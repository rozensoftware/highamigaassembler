# Contributing to HAS Compiler

Thank you for your interest in contributing to the HAS (High Assembler) project!

## Project Status

**Version 0.2 - In Constant Development**

This compiler is actively being developed. We welcome contributions, bug reports, and suggestions.

## How to Contribute

### Reporting Bugs

When reporting bugs, please include:

1. **HAS version**: Check with `python -m hasc.cli --help`
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
git clone [repository-url]
cd highamigassembler

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
- Follow 68000 calling convention
- Use RegisterAllocator for register management
- Generate comments in assembly for debugging
- Test generated assembly with vasm

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
   # Test with examples
   python -m hasc.cli examples/*.has
   
   # Verify no regressions
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

Current focus areas (Version 0.2):

#### High Priority
- **Test Suite**: Automated testing framework
- **Error Messages**: More informative validation errors
- **Optimization**: Peephole optimizer improvements
- **Documentation**: More examples and tutorials

#### Medium Priority
- **Standard Library**: Common utility functions
- **Code Samples**: Real-world Amiga programs
- **Build Tools**: Improved build scripts
- **VSCode Extension**: Syntax highlighting, snippets

#### Long-term
- **Floating Point**: Software FP library integration
- **Nested Structs**: Enhanced struct support
- **Cross-procedure Optimization**: Inlining, dead code elimination
- **Debugger Support**: Debug symbol generation

## Project Structure

Understanding the codebase:

```
hasc/
├── cli.py              # Command-line interface
├── parser.py           # Lark grammar and AST builder
├── ast.py              # AST node definitions
├── validator.py        # Semantic analysis (2-pass)
├── codegen.py          # Code generation (2500+ lines)
└── preprocessor.py     # Include and directive processing
```

### Compilation Pipeline

1. **Parse**: Lark converts `.has` source to parse tree
2. **Transform**: ASTBuilder creates typed AST
3. **Validate**: Two-pass semantic checking
4. **Generate**: Walk AST emitting 68000 assembly

Key concepts:
- **proc vs func**: `proc` defines, `func` forward-declares
- **Sections**: code, data, bss separated
- **Register Allocation**: d0-d7 (data), a0-a6 (address)
- **Calling Convention**: Stack-based with register parameters

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
