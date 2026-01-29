# Installation Guide for HAS Compiler

## System Requirements

- **Python**: 3.8 or higher
- **Operating System**: Linux, macOS, or Windows with WSL
- **Optional Tools**: vasm and vlink for assembly/linking

## Installation Steps

### 1. Install Python Dependencies

Navigate to the HAS directory and install required packages:

```bash
pip install -r requirements.txt
```

This will install:
- `lark-parser` - For parsing HAS source files

### 2. Verify Installation

Test the compiler installation:

```bash
python -m hasc.cli --help
```

You should see the HAS compiler help message.

### 3. Test with Example

Compile a simple example:

```bash
python -m hasc.cli examples/add.has -o test.s
```

If successful, you'll have a `test.s` assembly file.

### 4. (Optional) Install vasm and vlink

To create executable Amiga programs, you need the vasm assembler and vlink linker:

#### Linux/macOS:

Download and build from source:
```bash
# vasm
wget http://sun.hasenbraten.de/vasm/release/vasm.tar.gz
tar xzf vasm.tar.gz
cd vasm
make CPU=m68k SYNTAX=mot
sudo cp vasmm68k_mot /usr/local/bin/

# vlink
wget http://sun.hasenbraten.de/vlink/release/vlink.tar.gz
tar xzf vlink.tar.gz
cd vlink
make
sudo cp vlink /usr/local/bin/
```

#### Verify vasm/vlink:

```bash
vasmm68k_mot -h
vlink -h
```

### 5. Build Complete Example

With vasm/vlink installed:

```bash
# Compile HAS to assembly
python -m hasc.cli examples/add.has -o add.s

# Assemble and link
./scripts/build.sh add.s add.o add
```

## Troubleshooting

### Import Error: No module named 'lark'

Install dependencies:
```bash
pip install -r requirements.txt
```

### Permission Denied on scripts/build.sh

Make it executable:
```bash
chmod +x scripts/build.sh
```

### vasm/vlink not found

Ensure they are in your PATH or use full paths in scripts/build.sh

## Development Setup

For compiler development:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests (if available)
python -m pytest tests/
```

## Quick Test

Create a test file `test.has`:

```has
code main:
    proc main() -> int {
        var x:int = 42;
        return x;
    }
```

Compile it:
```bash
python -m hasc.cli test.has -o test.s
```

Check the generated `test.s` file - it should contain valid 68000 assembly code.

## Next Steps

- Read [README.md](README.md) for language overview
- Check [QUICK_START_ALL_PHASES.md](QUICK_START_ALL_PHASES.md) for detailed tutorial
- Explore examples in the `examples/` directory
- Review [COMPILER_DEVELOPERS_GUIDE.md](COMPILER_DEVELOPERS_GUIDE.md) for internals
