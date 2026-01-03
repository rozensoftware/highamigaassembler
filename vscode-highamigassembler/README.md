# High Amiga Assembler VS Code Extension

VS Code syntax highlighting and code navigation for the High Assembler (HAS) language targeting Motorola 68000 (Amiga).

This extension provides a complete development environment for HAS language, including syntax highlighting, intelligent code navigation, and hover information for cross-file procedure lookups.

## About This Extension

**Publisher:** Piotr Rozentreter  
**Language:** High Amiga Assembler (HAS)  
**Platform:** VS Code 1.85.0+  
**License:** MIT  

The extension enables developers to work efficiently with HAS source files by offering features like cross-file navigation, definition lookup, and reference finding—essential for managing large assembly projects with multiple modules.

## Features

### Syntax Highlighting
- Keywords from the language grammar: sections, procedures, control flow, macros, directives, and register hints
- Number formats: decimal, `$`/`0x` hex, and `%` binary
- Strings, comments (`//`), size suffixes (`.b`, `.w`, `.l`), registers (`d0-d7`, `a0-a7`)

### Code Navigation

#### Follow Link (Ctrl+Click) ⭐
**Click while holding Ctrl on any procedure name to jump to its definition**
- Works for:
  - Local procedures in the same file
  - Procedures in other `.has` files in the workspace
  - Assembly labels in `.s` (assembler) files
- Automatically searches the workspace to find the definition

#### Go to Definition (F12)
- Press **F12** while cursor is on a procedure name to jump to definition
- Same as Ctrl+Click navigation

#### Find References (Shift+F12)
- Press **Shift+F12** to find all references to a procedure
- Shows count and navigates through all usages

### Hover Information
- Hover over procedure names to see their signature
- Displays parameters and return type
- Shows whether it's a definition (`proc`) or forward declaration (`func`)

## Keybindings

| Action | Shortcut |
|--------|----------|
| Go to Definition | **F12** |
| Go to Definition | **Ctrl+Click** |
| Find References | **Shift+F12** |
| Go Back | **Ctrl+Alt+Left** |

## Quick Examples

### Cross-File Navigation

**game.has:**
```has
extern func update_graphics(x: long) -> long;

code game:
    proc main() -> long {
        update_graphics(100);  // Ctrl+Click jumps to graphics.has
        return 0;
    }
```

**graphics.has:**
```has
code graphics:
    proc update_graphics(x: long) -> long {
        return 0;
    }
```

### Assembly File Integration

**game.has:**
```has
extern func TakeSystem() -> long;  // Ctrl+Click jumps to takeover.s

code app:
    proc main() -> long {
        TakeSystem();
        return 0;
    }
```

**takeover.s:**
```asm
TakeSystem:
    movem.l d0-a6,-(sp)
    rts
```

## Installation

### From VS Code Marketplace
1. Open VS Code
2. Go to **Extensions** (Ctrl+Shift+X)
3. Search for "High Amiga Assembler"
4. Click **Install**
5. Reload VS Code if prompted

### From Source
1. Install `vsce`: `npm install -g @vscode/vsce`
2. Package: `vsce package` (produces `.vsix`)
3. Install: `code --install-extension <file>.vsix`
4. Reload VS Code

### Development Mode
1. Open extension folder in VS Code
2. Press **F5** to launch Extension Host (test instance)
3. Open a `.has` file to test

## Architecture

- **Entry point:** `extension.js`
- **DefinitionProvider** - Locates procedure definitions (Ctrl+Click, F12)
- **HoverProvider** - Shows signatures on hover
- **ReferenceProvider** - Finds all usages (Shift+F12)
- **Grammar:** `syntaxes/highamigassembler.tmLanguage.json`
- **Commands & keybindings:** `package.json`

### Search Order

1. Current file for procedure definitions
2. All `.has` files in workspace
3. All `.s` (assembly) files in workspace

## Limitations

- Case sensitive (procedure names must match exactly)
- Pattern matching only (simple regex, not full AST)
- Workspace scope only (no external libraries)
- No rename refactoring yet

## Version History

### 0.1.0
- Definition provider (Ctrl+Click, F12)
- Hover information (signatures)
- Reference provider (Shift+F12)
- VS Code Marketplace icon

### 0.0.1
- Syntax highlighting only

## Contributing

Issues, feature requests, and contributions are welcome! Please refer to the main project repository for contribution guidelines.

## Related Resources

- [High Amiga Assembler Main Project](https://github.com/highamiga/highamigassembler)
- [Amiga Motorola 68000 Documentation](https://en.wikipedia.org/wiki/Amiga)

## License

MIT
