const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

/**
 * DefinitionProvider for HAS language
 * Provides "Go to Definition" functionality via Ctrl+click or F12
 */
class HasDefinitionProvider {
    async provideDefinition(document, position, token) {
        const word = document.getWordRangeAtPosition(position);
        if (!word) {
            return null;
        }

        const procedureName = document.getText(word);
        
        // Get the workspace folder
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
        if (!workspaceFolder) {
            return null;
        }

        // Try to find in the current file first
        const localDef = this.findDefinitionInFile(document.getText(), procedureName, document.uri);
        if (localDef) {
            return localDef;
        }

        // Try to find in other .has files in the workspace
        const hasFiles = await this.findFilesInWorkspace(workspaceFolder.uri, '**/*.has');
        for (const fileUri of hasFiles) {
            if (fileUri.fsPath === document.uri.fsPath) {
                continue; // Skip the current file
            }
            
            try {
                const fileDoc = await vscode.workspace.openTextDocument(fileUri);
                const def = this.findDefinitionInFile(fileDoc.getText(), procedureName, fileUri);
                if (def) {
                    return def;
                }
            } catch (e) {
                // Skip files that can't be opened
            }
        }

        // Try to find in associated .s (assembly) files
        const assemblyFiles = await this.findFilesInWorkspace(workspaceFolder.uri, '**/*.s');
        for (const fileUri of assemblyFiles) {
            try {
                const fileDoc = await vscode.workspace.openTextDocument(fileUri);
                const def = this.findDefinitionInAssembly(fileDoc.getText(), procedureName, fileUri);
                if (def) {
                    return def;
                }
            } catch (e) {
                // Skip files that can't be opened
            }
        }

        return null;
    }

    /**
     * Find procedure definition in HAS source code
     * Matches: proc name(...) -> type { ... } or native proc name(...) -> type { ... }
     */
    findDefinitionInFile(fileContent, procedureName, fileUri) {
        // Match: proc name(params...) -> type { or native proc name(params...) -> type {
        const procPattern = new RegExp(`\\b(?:native\\s+)?proc\\s+${this.escapeRegex(procedureName)}\\s*\\(`, 'g');
        let match;

        while ((match = procPattern.exec(fileContent)) !== null) {
            const startPos = match.index;
            const lineNum = fileContent.substring(0, startPos).split('\n').length - 1;
            const charPos = startPos - fileContent.lastIndexOf('\n', startPos - 1) - 1;
            
            return new vscode.Location(
                fileUri,
                new vscode.Position(lineNum, charPos)
            );
        }

        return null;
    }

    /**
     * Find procedure definition in 68000 assembly file
     * Matches: label: or name: (assembly labels)
     */
    findDefinitionInAssembly(fileContent, procedureName, fileUri) {
        // In assembly, look for the label that matches the procedure name
        const asmPattern = new RegExp(`^\\s*${this.escapeRegex(procedureName)}:\\s*$`, 'gm');
        let match;

        while ((match = asmPattern.exec(fileContent)) !== null) {
            const startPos = match.index;
            const lineNum = fileContent.substring(0, startPos).split('\n').length - 1;
            
            return new vscode.Location(
                fileUri,
                new vscode.Position(lineNum, 0)
            );
        }

        return null;
    }

    /**
     * Find all files matching a glob pattern in the workspace
     */
    async findFilesInWorkspace(workspaceUri, pattern) {
        try {
            return await vscode.workspace.findFiles(pattern, null, 100);
        } catch (e) {
            return [];
        }
    }

    /**
     * Escape special regex characters
     */
    escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
}

/**
 * Hover provider for HAS language
 * Shows procedure information on hover
 */
class HasHoverProvider {
    provideHover(document, position, token) {
        const word = document.getWordRangeAtPosition(position);
        if (!word) {
            return null;
        }

        const procedureName = document.getText(word);
        
        // Try to find the procedure signature (including native)
        const procPattern = new RegExp(`\\b(native\\s+)?proc\\s+${this.escapeRegex(procedureName)}\\s*\\(([^)]*)\\)\\s*->\\s*(\\w+)`, 'g');
        let match = procPattern.exec(document.getText());

        if (match) {
            const nativeKeyword = match[1] ? 'native ' : '';
            const params = match[2].trim();
            const returnType = match[3];
            
            let markdown = new vscode.MarkdownString(`\`\`\`has\n${nativeKeyword}proc ${procedureName}(${params}) -> ${returnType}\n\`\`\``);
            markdown.isTrusted = true;
            
            return new vscode.Hover(markdown);
        }

        // Try to find forward declaration (func, including native)
        const funcPattern = new RegExp(`\\b(native\\s+)?func\\s+${this.escapeRegex(procedureName)}\\s*\\(([^)]*)\\)\\s*->\\s*(\\w+)`, 'g');
        match = funcPattern.exec(document.getText());

        if (match) {
            const nativeKeyword = match[1] ? 'native ' : '';
            const params = match[2].trim();
            const returnType = match[3];
            
            let markdown = new vscode.MarkdownString(`\`\`\`has\n${nativeKeyword}func ${procedureName}(${params}) -> ${returnType} // Forward declaration\n\`\`\``);
            markdown.isTrusted = true;
            
            return new vscode.Hover(markdown);
        }

        return null;
    }

    escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
}

/**
 * References provider for HAS language
 * Shows all references to a procedure
 */
class HasReferenceProvider {
    async provideReferences(document, position, context, token) {
        const word = document.getWordRangeAtPosition(position);
        if (!word) {
            return [];
        }

        const procedureName = document.getText(word);
        const references = [];

        // Get the workspace folder
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
        if (!workspaceFolder) {
            return [];
        }

        // Search in all .has files
        const hasFiles = await vscode.workspace.findFiles('**/*.has', null, 100);
        for (const fileUri of hasFiles) {
            try {
                const fileDoc = await vscode.workspace.openTextDocument(fileUri);
                const fileContent = fileDoc.getText();
                
                // Find all references (calls) to this procedure
                const pattern = new RegExp(`\\b${this.escapeRegex(procedureName)}\\s*\\(`, 'g');
                let match;

                while ((match = pattern.exec(fileContent)) !== null) {
                    const startPos = match.index;
                    const lineNum = fileContent.substring(0, startPos).split('\n').length - 1;
                    const charPos = startPos - fileContent.lastIndexOf('\n', startPos - 1) - 1;
                    
                    const range = new vscode.Range(
                        new vscode.Position(lineNum, charPos),
                        new vscode.Position(lineNum, charPos + procedureName.length)
                    );
                    
                    references.push(new vscode.Location(fileUri, range));
                }
                
                // Also find definitions
                if (context.includeDeclaration) {
                    const defPattern = new RegExp(`\\bproc\\s+${this.escapeRegex(procedureName)}\\s*\\(`, 'g');
                    while ((match = defPattern.exec(fileContent)) !== null) {
                        const startPos = match.index + fileContent.substring(match.index, match.index + 10).indexOf(procedureName);
                        const lineNum = fileContent.substring(0, startPos).split('\n').length - 1;
                        const charPos = startPos - fileContent.lastIndexOf('\n', startPos - 1) - 1;
                        
                        const range = new vscode.Range(
                            new vscode.Position(lineNum, charPos),
                            new vscode.Position(lineNum, charPos + procedureName.length)
                        );
                        
                        references.push(new vscode.Location(fileUri, range));
                    }
                }
            } catch (e) {
                // Skip files that can't be opened
            }
        }

        return references;
    }

    escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
}

/**
 * Activate the extension
 */
function activate(context) {
    console.log('HAS Language Extension activated');

    // Register definition provider
    const definitionProvider = new HasDefinitionProvider();
    context.subscriptions.push(
        vscode.languages.registerDefinitionProvider(
            { scheme: 'file', language: 'highamigassembler' },
            definitionProvider
        )
    );

    // Register hover provider
    const hoverProvider = new HasHoverProvider();
    context.subscriptions.push(
        vscode.languages.registerHoverProvider(
            { scheme: 'file', language: 'highamigassembler' },
            hoverProvider
        )
    );

    // Register references provider
    const referenceProvider = new HasReferenceProvider();
    context.subscriptions.push(
        vscode.languages.registerReferenceProvider(
            { scheme: 'file', language: 'highamigassembler' },
            referenceProvider
        )
    );

    // Register command: Go to Definition
    context.subscriptions.push(
        vscode.commands.registerCommand('highamigassembler.goToDefinition', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                return;
            }

            const definition = await definitionProvider.provideDefinition(
                editor.document,
                editor.selection.active,
                null
            );

            if (definition) {
                const doc = await vscode.workspace.openTextDocument(definition.uri);
                await vscode.window.showTextDocument(doc);
                
                const newEditor = vscode.window.activeTextEditor;
                if (newEditor) {
                    newEditor.selection = new vscode.Selection(
                        definition.range.start,
                        definition.range.start
                    );
                    newEditor.revealRange(definition.range);
                }
            } else {
                vscode.window.showInformationMessage('Definition not found');
            }
        })
    );

    // Register command: Find References
    context.subscriptions.push(
        vscode.commands.registerCommand('highamigassembler.findReferences', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                return;
            }

            const refProvider = new HasReferenceProvider();
            const references = await refProvider.provideReferences(
                editor.document,
                editor.selection.active,
                { includeDeclaration: true },
                null
            );

            if (references.length > 0) {
                // Show results in "Find Results" panel would require a custom view
                // For now, open the first reference
                const ref = references[0];
                const doc = await vscode.workspace.openTextDocument(ref.uri);
                await vscode.window.showTextDocument(doc);
                
                const newEditor = vscode.window.activeTextEditor;
                if (newEditor) {
                    newEditor.selection = new vscode.Selection(
                        ref.range.start,
                        ref.range.end
                    );
                    newEditor.revealRange(ref.range);
                }
                
                vscode.window.showInformationMessage(`Found ${references.length} reference(s)`);
            } else {
                vscode.window.showInformationMessage('No references found');
            }
        })
    );
}

/**
 * Deactivate the extension
 */
function deactivate() {}

module.exports = {
    activate,
    deactivate
};
