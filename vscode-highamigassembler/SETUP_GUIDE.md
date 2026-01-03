# HAS VS Code Extension - Setup and Usage Guide

## Quick Start

### 1. Install the Extension

#### Option A: From Source (Development)
```bash
cd vscode-highamigassembler

# Install dependencies (if needed)
npm install

# Open in VS Code for testing
code .

# Press F5 to launch Extension Host
```

#### Option B: Package and Install
```bash
# Install vsce globally (one-time)
npm install -g @vscode/vsce

# From extension folder
cd vscode-highamigassembler
vsce package

# Install the .vsix file
code --install-extension vscode-highamigassembler-0.1.0.vsix
```

### 2. Verify Installation

1. Open a `.has` file in VS Code
2. You should see syntax highlighting
3. Try one of the keyboard shortcuts below

## Features

### Follow Link - Ctrl+Click ⭐ (New!)

Hold **Ctrl** and click on any procedure name to jump to its definition:

```has
code game:
    proc helper() -> long {
        return 100;
    }
    
    proc main() -> long {
        helper();  // Ctrl+Click on "helper" jumps to line 2
        return 0;
    }
```

**What it finds:**
- Procedures in the same file
- Procedures in other `.has` files
- Assembly labels in `.s` files

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **F12** | Go to Definition (place cursor on procedure name) |
| **Ctrl+Click** | Go to Definition (click on procedure name) |
| **Shift+F12** | Find All References (place cursor on name) |
| **Ctrl+Alt+Left** | Go Back (standard VS Code) |

## Example Workflows

### Scenario 1: Navigate Local Procedures

**File: game.has**
```has
code game:
    proc setup() -> long {
        return init_variables();  // Press F12 to jump to init_variables
    }
    
    proc init_variables() -> long {
        return 0;
    }
    
    proc main() -> long {
        setup();  // Ctrl+Click to jump to setup
        return 0;
    }
```

1. Click on `setup` in main()
2. Press **F12** → jumps to `proc setup()` definition
3. Click on `init_variables()` call
4. Press **F12** → jumps to `proc init_variables()` definition
5. Press **Ctrl+Alt+Left** → back to previous location

### Scenario 2: Navigate Cross-File

**File: main.has**
```has
extern func render(x: long) -> long;

code app:
    proc main() -> long {
        return render(100);  // Ctrl+Click jumps to graphics.has
    }
```

**File: graphics.has**
```has
code graphics:
    proc render(x: long) -> long {
        // Implementation
        return 0;
    }
```

1. In main.has, Ctrl+Click on `render` call
2. Extension searches all `.has` files
3. Opens graphics.has at `proc render()` definition

### Scenario 3: Assembly Integration

**File: game.has**
```has
extern func TakeSystem() -> long;  // Ctrl+Click jumps to takeover.s

code app:
    proc main() -> long {
        TakeSystem();
        return 0;
    }
```

**File: takeover.s**
```asm
TakeSystem:
    movem.l d0-a6,-(sp)
    ; Implementation
    rts
```

1. In game.has, Ctrl+Click on `TakeSystem`
2. Extension searches `.s` files
3. Opens takeover.s at `TakeSystem:` label

### Scenario 4: Find All References

Find every place a procedure is used:

```has
code app:
    proc utility(x: long) -> long { return x * 2; }
    
    proc process() -> long {
        var a: long = utility(5);      // Reference 1
        var b: long = utility(10);     // Reference 2
        return 0;
    }
    
    proc main() -> long {
        return utility(100);  // Reference 3
    }
```

1. Place cursor on `utility`
2. Press **Shift+F12**
3. Shows: "Found 4 reference(s)" (includes 1 definition + 3 calls)
4. Navigate through each with arrow keys or mouse

## Hover Information

Hover your mouse over any procedure name to see its signature:

```has
code demo:
    proc calculate(a: long, b: long) -> long {
        return a + b;
    }
    
    proc main() -> long {
        var x = calculate(5, 3);  // Hover over "calculate" to see signature
        return x;
    }
```

**Hover shows:**
```
proc calculate(a: long, b: long) -> long
```

For forward declarations, also shows:
```
func helper(x: long) -> long // Forward declaration
```

## Troubleshooting

### "Definition not found"
- **Check:** Procedure name matches exactly (case-sensitive)
- **Check:** File is in the workspace (not external)
- **Check:** File has `.has` or `.s` extension

### F12 or Ctrl+Click not working
- **Try:** Ensure cursor is on the procedure name
- **Try:** Reload VS Code (`Ctrl+R`)
- **Check:** Language is recognized as "highamigassembler" (bottom status bar)

### Extension not activating
- **Open** any `.has` file to trigger activation
- **Check** Output panel: VS Code → View → Output → select "HAS Language Extension"

## How It Works

The extension uses three providers:

### 1. Definition Provider
- Finds procedure definitions when you press F12 or Ctrl+Click
- Searches in this order:
  1. Current file
  2. All `.has` files in workspace
  3. All `.s` assembly files in workspace

### 2. Hover Provider
- Shows procedure signature when you hover
- Displays parameters, return type, and declaration type

### 3. Reference Provider
- Finds all usages of a procedure when you press Shift+F12
- Searches all `.has` files in workspace

## Development

To customize the extension:

### Edit Search Patterns
File: `extension.js`
- Line ~50: `findDefinitionInFile()` - HAS procedure pattern
- Line ~75: `findDefinitionInAssembly()` - Assembly label pattern

### Add New Commands
File: `package.json` - Add to `contributes.commands` array
File: `extension.js` - Add to `activate()` function

### Modify Keybindings
File: `package.json` - Edit `contributes.keybindings`

## Configuration

### Workspace Settings
Add to `.vscode/settings.json`:
```json
{
    "editor.defaultFormatter": null,
    "[highamigassembler]": {
        "editor.formatOnSave": false
    }
}
```

### Keybinding Customization
File: `.vscode/keybindings.json`
```json
{
    "key": "ctrl+alt+d",
    "command": "highamigassembler.goToDefinition",
    "when": "editorTextFocus && editorLangId == highamigassembler"
}
```

## Performance Notes

- Searches limited to 100 files per pattern (configurable in `extension.js`)
- Pattern matching is fast for typical 50KB files
- Assembly file searches are optional (can be disabled in code)

## Future Enhancements

- [ ] Refactor/Rename procedure (all occurrences)
- [ ] Workspace symbol search (Ctrl+T)
- [ ] Struct field navigation
- [ ] Macro expansion preview
- [ ] Snippets for common patterns
- [ ] Diagnostics (linting)

## Support

For issues or suggestions:
1. Check existing issues in repository
2. Enable debug logging in VS Code Output
3. Include `.has` file snippet showing the issue
4. Include VS Code version (`Help → About`)

## License

MIT - See LICENSE file in extension folder
