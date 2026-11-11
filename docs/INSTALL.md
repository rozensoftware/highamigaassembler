# Installation Guide for HAS Compiler

## System Requirements

- **Python**: 3.8 or higher
- **Operating System**: Linux, macOS, or Windows with WSL
- **Optional Tools**: vasm and vlink for assembly/linking

## Installation Steps

### 1. Install HAS

Install [pipx](https://pipx.pypa.io/) once. It installs the command-line compiler in an isolated
environment and adds its command directory to your user PATH:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Open a new terminal, then install the wheel attached to the selected GitHub Release:

```powershell
pipx install https://github.com/rozensoftware/highamigaassembler/releases/download/vX.Y.Z/high_amiga_assembler-X.Y.Z-py3-none-any.whl
```

Replace `X.Y.Z` with the release version. To upgrade, run `pipx upgrade hasc`; to remove HAS, run
`pipx uninstall hasc`.

As an alternative when pipx is unavailable:

```powershell
py -m pip install --user https://github.com/rozensoftware/highamigaassembler/releases/download/vX.Y.Z/high_amiga_assembler-X.Y.Z-py3-none-any.whl
```

### 2. Verify Installation

Test the compiler installation:

```powershell
hasc --help
hasc --version
```

You should see the HAS compiler help message.

### 3. Test with Example

Compile a simple example to assembly:

```bash
hasc examples/add.has -o test.s
```

If successful, you'll have a `test.s` assembly file. With `vasm` and `vlink` on
`PATH`, you can also build an Amiga executable (or bootable ADF) in one step —
see [§5](#5-build-complete-example).

### Packaged Resources

The release wheel also includes the HAS assembly libraries, example programs, asset tools, and
Linux build scripts. Their installation directory depends on the Python environment used by pipx
or pip. For a pipx installation, locate the package with:

```bash
pipx runpip hasc show high-amiga-assembler
```

The resources are installed below that environment's `share/high-amiga-assembler/` directory:
`lib/`, `examples/`, `tools/`, `scripts/`, and `guicreator/`. Copy an example into a writable
project directory before changing it. Prefer `hasc … --exe` / `--adf` for one-shot builds.
Legacy `scripts/*.sh` helpers are Linux-oriented; both paths require separately installed
`vasm` and `vlink` (ADF also needs `amitools` / `xdftool`).

All packaged Python asset tools are available as `has-*` commands, for example:

```bash
has-bob-importer image.png 5 --outdir include
has-sprite-importer sprite.png --outdir include
has-tile-importer tiles.png --tile-width 16 --help
has-tiled-map-importer level.tmx --layer Ground --outdir build/gen
has-gui-creator --help
```

Install HAS with its `tools` extra when a converter needs Pillow or amitools. The supplied shell
scripts remain resource files only; they are not registered as commands. Musashi runtime files are
not part of the release package.

### 4. Install vasm and vlink separately to assemble and link

HAS creates `.s` assembly files but does not package, install, download, or redistribute the vasm
assembler or vlink linker. Download them separately, add their directory to `PATH`, and verify:

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

With vasm/vlink installed, build an Amiga hunk executable in one step:

```bash
hasc examples/mintest.has -o mintest.s --exe mintest.exe
```

`--cpu 68000` (default) or `--cpu 68020` is passed through to both codegen and
vasm (`-m68000` / `-m68020`). Programs that declare `extern` symbols auto-link
matching files from `lib/` when providers are known.

Optional bootable ADF (requires amitools / xdftool; install with
`pip install amitools` or the package `tools` extra):

```bash
hasc examples/mintest.has -o mintest.s --adf disks/mintest.adf
```

The ADF includes the executable and `S/startup-sequence` so an emulator or
real Amiga boots straight into the program.

Legacy helpers still work: `./scripts/build.sh` (assemble/link) and
`./scripts/create_disk.sh` (ADF from an existing exe).

### 6. Optional: Linux-Only Musashi Runtime Test Tier

This tier is useful for selected tests that require real m68k runtime
execution, not just compile/link validation.

Prerequisites:
- Linux (native or WSL)
- C compiler (`gcc` or `clang`)
- `vasmm68k_mot`

Commands:

```bash
# Prepare pinned Musashi source
./scripts/setup_musashi.sh

# Build the local Musashi runner
./scripts/build_musashi_runner.sh

# Run selected runtime tests
./scripts/test_runtime_musashi.sh
```

To update the pinned Musashi version later:

```bash
./scripts/update_musashi_pin.sh <git-ref>
# example: ./scripts/update_musashi_pin.sh master
```

For full details, see [docs/MUSASHI_RUNTIME_TESTING.md](MUSASHI_RUNTIME_TESTING.md).

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

# Run example-driven smoke checks
python -m hasc.cli examples/add.has -o /tmp/add.s
python -m hasc.cli examples/shift_operators_demo.has -o /tmp/shift.s
```

## Maintainer Release Checklist

1. Update `hasc.__version__` and add a user-facing entry under `Unreleased` in
    [CHANGELOG.md](CHANGELOG.md).
2. Run `python -m pytest tests -q`, then compile a smoke example with both `--cpu 68000` and
    `--cpu 68020`.
3. On Linux, run `bash scripts/build_has_package.sh`. It builds the wheel and source distribution
    outside the repository's `build/` directory, validates them with Twine, and writes them to
    `dist/`. Pass an output directory as its first argument when needed.
4. Install the produced wheel into a clean environment to verify `hasc --version` and a sample
    compilation.
5. Commit the release changes, create a matching tag such as `v0.9.12`, and push the tag. The
    GitHub Release workflow verifies the tag/version match, rebuilds, tests, and attaches the
    wheel and source distribution to the release.
6. In a clean Windows terminal, install the attached wheel with pipx, verify `where hasc`, and
    compile an example. Confirm that the release notes still state the separate `vasm`/`vlink`
    requirement for assembly and linking.

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

- Read [README.md](../README.md) for language overview
- Check [DEVELOPERS_GUIDE.md](DEVELOPERS_GUIDE.md) for a detailed language tutorial
- Explore examples in the `examples/` directory
- Review [COMPILER_DEVELOPERS_GUIDE.md](COMPILER_DEVELOPERS_GUIDE.md) for internals
