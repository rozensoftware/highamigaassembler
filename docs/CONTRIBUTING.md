# Contributing to HAS Compiler

Thank you for your interest in contributing to the HAS (High Assembler) project!

## Project Status

**Version 0.9.12 - Feature-frozen; stabilizing toward 1.0.0**

Bug reports, documentation improvements, examples, and regression fixes are
welcome. Proposals that expand compiler behavior should account for the
project's feature-frozen stabilization phase.

## How to Contribute

### Reporting Bugs

When reporting bugs, please include:

1. **HAS version**: Check with `hasc --version` or `python -m hasc.cli --version`
2. **Minimal reproducible example**: A small `.has` file that demonstrates the issue
3. **Expected behavior**: What you expected to happen
4. **Actual behavior**: What actually happened
5. **Generated assembly** (if applicable): The `.s` output file
6. **Error messages**: Complete error output with line numbers
7. **Environment**: OS, Python version

### Suggesting Features

For feature requests:

1. Check existing documentation to see if the feature already exists
2. Describe the use case clearly
3. Provide example syntax (if applicable)
4. Explain how it would improve the language

### Code Contributions

#### Before Starting

1. Check if someone is already working on the feature/fix
2. Discuss major changes before implementing
3. Review existing code style and patterns
4. Read [COMPILER_DEVELOPERS_GUIDE.md](COMPILER_DEVELOPERS_GUIDE.md) for architecture

#### Development Setup

```bash
# Clone the repository
git clone https://github.com/rozensoftware/highamigaassembler.git
cd highamigaassembler

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run existing examples to verify setup
python -m hasc.cli examples/add.has -o test.s
```

#### Code Guidelines

**Parser Changes** (`hasc/parser.py`):
- Update GRAMMAR string following Lark EBNF syntax
- Add corresponding transformer methods in ASTBuilder
- Test with existing examples first

**AST Changes** (`hasc/ast.py`):
- Use dataclasses for new node types
- Include type hints
- Update visitor patterns in validator and codegen

**Validator Changes** (`hasc/validator.py`):
- Maintain two-pass structure (symbol collection, then validation)
- Provide clear error messages with line numbers
- Test with both valid and invalid inputs

**Code Generator Changes** (`hasc/codegen.py`):
- Preserve the declared HAS/external calling convention and use the register
  allocator for scratch allocation where appropriate
- Keep 68000 output free of 68020-only instructions; add paired target checks
  when code generation may differ
- Add or update tests for generated assembly; assemble with the matching vasm
  CPU flag when available

**Testing**:
- Add new examples in `examples/` directory
- Create both positive (valid) and negative (error) test cases
- Verify assembly output with vasm (if available)
- Document expected behavior in comments

#### Code Style

- **Python**: Follow PEP 8 style guidelines
- **Line Length**: 100 characters max (flexible for long strings)
- **Type Hints**: Use where appropriate
- **Comments**: Explain "why" not "what"
- **Docstrings**: For public functions and classes

#### Commit Messages

```
Short summary (50 chars or less)

More detailed explanation if necessary. Wrap at 72 characters.
Explain the problem this commit solves and why this approach was chosen.

- Bullet points are fine
- Use present tense ("Add feature" not "Added feature")
- Reference issues/PRs if applicable
```

### Pull Request Process

1. **Fork and Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**:
   - Write clear, focused commits
   - Add/update tests and examples
   - Update documentation

3. **Test Thoroughly**:
   ```bash
   # Test one example quickly
   python -m hasc.cli examples/add.has -o /tmp/test.s

   # Verify no regressions (split positive/negative example gate)
   ./scripts/tests/test_examples_split.sh

   # Or compile all root examples in a loop
   for f in examples/*.has; do python -m hasc.cli "$f" -o /tmp/test.s || exit 1; done

   # VBCC interop regression wrappers
   ./scripts/tests/test_vbcc_interop.sh
   ./scripts/tests/test_vbcc_interop.ps1
   ```

4. **Update Documentation**:
   - Update relevant .md files
   - Add examples if introducing new syntax
   - Update CHANGELOG.md

5. **Submit PR**:
   - Clear title and description
   - Link related issues
   - List all changes
   - Explain design decisions

### Areas Needing Help

Useful stabilization and contribution areas:

#### High Priority
- **Regression Coverage**: Keep compiler and asset-import checks green on both CPU targets
- **Code Generation**: Improve correctness, diagnostics, and optimization quality
- **Asset Workflows**: Expand practical graphics, music, and sound examples

#### Medium Priority
- **Standard Library**: Add reusable routines for Amiga applications
- **Code Samples**: Validate more real-world programs on emulators and hardware
- **Developer Tools**: Improve packaging, build scripts, and editor support

#### Future proposals
- **Runtime fixed-point operations**: Existing Q16.16 literal conversion is
  compile-time; runtime arithmetic would need a separate design
- **Nested Structs**: Enhanced struct support
- **Cross-procedure Optimization**: For example, inlining
- **Debugger Support**: Debug symbol generation

## Project Structure

Understanding the codebase:

```
hasc/
├── cli.py              # Command-line interface
├── parser.py           # Lark grammar and AST builder
├── ast.py              # AST node definitions
├── validator.py        # Semantic validation and resolution
├── target.py           # CPU target capabilities
├── indexed_address.py  # Target-aware effective-address lowering
├── codegen.py          # Code generation and register management
├── codegen_indexed_address.py
├── register_allocator.py
├── macro_expander.py   # Macro expansion support
└── reachability.py     # Dead-procedure reachability analysis
```

### Compilation Pipeline

1. **Preprocess and parse**: Handle includes, conditional compilation, and
   asset imports; Lark and `ASTBuilder` create the AST.
2. **Validate and resolve**: Check declarations/uses and apply constant-resolved
   dimensions and sizes.
3. **Prune (optional)**: `--strip-unused-procs` performs conservative
   call-graph reachability analysis.
4. **Generate**: Emit assembly for `--cpu 68000` (default) or `--cpu 68020`.
5. **Build (optional)**: `--exe`/`--adf` invoke the separately installed
   assembler/linker and ADF tools.

Key concepts:
- **proc vs func**: `proc` defines, `func` forward-declares
- **Sections**: code, data, bss separated
- **Scratch Registers**: The allocator manages d0-d6 and a0-a2; d7 is reserved
  for DBcc loop counters, while a6/a7 have frame/stack roles.
- **Calling Convention**: Stack arguments by default; declared `__reg(...)`
  parameters use registers.

## Questions?

- Check documentation in the root directory
- Review examples for usage patterns
- Read [COMPILER_DEVELOPERS_GUIDE.md](COMPILER_DEVELOPERS_GUIDE.md) for internals

## Code of Conduct

- Be respectful and constructive
- Focus on the technical merit of ideas
- Help newcomers learn the codebase
- Assume good intentions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for helping make HAS better!**
