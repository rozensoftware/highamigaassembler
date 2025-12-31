# GitHub Publishing Guide

This guide explains how to publish the HAS Compiler to GitHub.

## Repository Setup

### 1. Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `has-compiler` (or your preferred name)
3. Description: "HAS - High Assembler for Motorola 68000 (Amiga)"
4. Choose visibility (Public recommended for open source)
5. **Do NOT** initialize with README (we have one)
6. Create repository

### 2. Initialize Git in Publish Folder

```bash
cd publish
git init
git add .
git commit -m "Initial release v0.2"
```

### 3. Add Remote and Push

```bash
# Replace USERNAME with your GitHub username
git remote add origin https://github.com/USERNAME/has-compiler.git
git branch -M main
git push -u origin main
```

## Repository Structure

The publish folder contains:

```
publish/
├── README.md              # Main documentation
├── LICENSE                # MIT License
├── VERSION                # Version information
├── CHANGELOG.md           # Version history
├── CONTRIBUTING.md        # Contribution guidelines
├── INSTALL.md             # Installation instructions
├── requirements.txt       # Python dependencies
├── .gitignore             # Git ignore rules
│
├── hasc/                  # Compiler source code
├── examples/              # Example programs (games excluded)
├── lib/                   # Standard library
├── templates/             # Jinja2 templates
├── scripts/               # Build scripts
├── docs/                  # Additional documentation
│
└── [Various .md files]    # Feature documentation
```

## GitHub Repository Settings

### Repository Description

```
HAS - High Assembler for Motorola 68000 (Amiga). A Python-based compiler providing high-level constructs for assembly programming with inline assembly support.
```

### Topics/Tags (Add these in repository settings)

```
amiga
motorola-68000
assembly-language
compiler
assembler
retro-computing
amiga-development
68000
python
code-generation
```

### About Section

- **Website**: (your project website if any)
- **License**: MIT
- **Languages**: Python, Assembly

## Create First Release

### Via GitHub Web Interface

1. Go to your repository
2. Click "Releases" → "Create a new release"
3. Tag version: `v0.2`
4. Release title: `HAS Compiler v0.2 - Initial Public Release`
5. Description:

```markdown
# HAS Compiler v0.2

First public release of HAS (High Assembler) - a high-level assembler for Motorola 68000 (Amiga).

## Highlights

- Complete 68000 code generation pipeline
- High-level programming constructs (variables, loops, functions)
- Inline assembly support
- Macro system and Python integration
- 60+ example programs
- Comprehensive documentation

## Installation

```bash
pip install -r requirements.txt
python -m hasc.cli examples/add.has -o output.s
```

See [INSTALL.md](INSTALL.md) for detailed instructions.

## Documentation

- [README.md](README.md) - Overview and quick start
- [QUICK_START_ALL_PHASES.md](QUICK_START_ALL_PHASES.md) - Complete tutorial
- [COMPILER_DEVELOPERS_GUIDE.md](COMPILER_DEVELOPERS_GUIDE.md) - Architecture

## Status

**In Constant Development** - This is an active project under continuous improvement.

## Requirements

- Python 3.8+
- lark-parser, jinja2
- Optional: vasm, vlink (for assembly/linking)
```

6. Attach files (optional): Create a zip of the publish folder
7. Check "This is a pre-release" (since in development)
8. Click "Publish release"

### Via Git Command Line

```bash
cd publish
git tag -a v0.2 -m "Version 0.2 - Initial public release"
git push origin v0.2
```

Then create the release on GitHub web interface.

## README Badges (Optional)

Add these to the top of README.md:

```markdown
![Version](https://img.shields.io/badge/version-0.2-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![Status](https://img.shields.io/badge/status-in%20development-yellow)
```

## GitHub Actions (Future Enhancement)

Create `.github/workflows/test.yml` for CI:

```yaml
name: Test HAS Compiler

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.8'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Test examples
        run: |
          for file in examples/*.has; do
            python -m hasc.cli "$file" -o test.s || exit 1
          done
```

## Promoting Your Project

### README Quality

Ensure your README includes:
- [x] Clear project description
- [x] Quick start guide
- [x] Installation instructions
- [x] Examples
- [x] Documentation links
- [x] License information
- [x] Development status

### Community Engagement

- Post on Amiga development forums
- Share on retro computing communities
- Reddit: r/amiga, r/retrobattlestations
- Twitter/Mastodon with #AmigaDev #RetroComputing

### Documentation Site (Optional)

Consider using GitHub Pages:
1. Settings → Pages
2. Source: Deploy from branch `main` / `docs` folder
3. Create docs/index.html from README.md

## Maintenance

### Regular Updates

- Keep CHANGELOG.md updated with each change
- Update VERSION file
- Tag releases consistently
- Respond to issues promptly
- Merge pull requests with proper review

### Version Numbering

Follow semantic versioning:
- **0.x.y** - Pre-1.0 development
- **x.0.0** - Major changes (breaking)
- **x.y.0** - New features (non-breaking)
- **x.y.z** - Bug fixes

## Example Publishing Workflow

```bash
# From project root
cd publish

# Initialize repository
git init
git add .
git commit -m "Initial release v0.2"

# Add remote (replace USERNAME)
git remote add origin https://github.com/USERNAME/has-compiler.git

# Push to GitHub
git branch -M main
git push -u origin main

# Create tag
git tag -a v0.2 -m "Version 0.2 - Initial public release"
git push origin v0.2

# Then create release on GitHub web interface
```

## Post-Publishing

1. **Verify Links**: Check all links in README work
2. **Test Installation**: Follow INSTALL.md on clean system
3. **Monitor Issues**: Respond to user feedback
4. **Update Documentation**: Keep improving based on questions

## Tips

- Use clear commit messages
- Keep master/main branch stable
- Use branches for new features
- Write good release notes
- Engage with contributors
- Keep documentation up-to-date

---

**Ready to publish!** 🚀

Your HAS Compiler is now ready for GitHub. The publish folder contains everything needed for a professional open-source release.
