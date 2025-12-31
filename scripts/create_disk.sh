#!/bin/bash

# create_disk.sh - Universal ADF disk creation script for HAS (High Amiga Assembler) projects
# Usage: ./create_disk.sh <diskname> <program_to_copy>
# 
# Uses xdftool from amitools for proper Amiga filesystem creation
#
# Arguments:
#   diskname      - Name of the ADF file to create (without .adf extension)
#   program       - Path to the executable program to copy
#
# Examples:
#   ./create_disk.sh MyGame build/launchers.exe
#   ./create_disk.sh MyDemo build/myprogram.exe

if [ $# -lt 2 ]; then
    echo "Usage: $0 <diskname> <program_to_copy>"
    echo ""
    echo "Arguments:"
    echo "  diskname      - Name of ADF file (without .adf)"
    echo "  program       - Path to executable program"
    echo ""
    echo "Examples:"
    echo "  $0 Launchers build/launchers.exe"
    echo "  $0 MyGame build/mygame.exe" 
    exit 1
fi

DISKNAME="$1"
PROGRAM="$2"
ADF_FILE="disks/${DISKNAME}.adf"

# Go to script directory then back to project root
SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "Creating ADF disk: $DISKNAME"
echo "Program: $PROGRAM"

# Check if program exists
if [ ! -f "$PROGRAM" ]; then
    echo "Error: Program '$PROGRAM' not found!"
    echo "Make sure to compile your HAS program first:"
    echo "  cd examples/games/launchers && make"
    exit 1
fi

# Check for xdftool (from amitools)
if ! command -v xdftool >/dev/null 2>&1; then
    echo "Error: xdftool not found!"
    echo "Installing amitools (contains xdftool)..."
    
    # Try to install amitools
    if ! pip3 install --user amitools >/dev/null 2>&1; then
        echo "Error: Failed to install amitools. Please install manually:"
        echo "  pip3 install amitools"
        exit 1
    fi
    echo "✅ amitools installed successfully"
fi

# Ensure disks directory exists
mkdir -p disks

# Remove existing ADF
rm -f "$ADF_FILE"

echo "Creating ADF with xdftool..."

PROG_SIZE=$(stat -c%s "$PROGRAM")
PROG_NAME=$(basename "$PROGRAM")

# Create ADF disk with xdftool (much simpler and more reliable!)
xdftool "$ADF_FILE" create + format "$DISKNAME" + write "$PROGRAM" "$PROG_NAME"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ ADF disk created successfully!"
    echo "📁 File: $ADF_FILE"
    echo "🎮 Program: $PROG_NAME (${PROG_SIZE} bytes)"
    echo "💾 Volume: $DISKNAME"
    echo "🔧 Tool: xdftool (amitools)"
    echo ""
    echo "📋 Contents:"
    xdftool "$ADF_FILE" list
    echo ""
    echo "Usage:"
    echo "  • Load $ADF_FILE in FS-UAE or other Amiga emulator"
    echo "  • Program '$PROG_NAME' will be visible and executable"
    echo "  • Perfect compatibility with real Amiga systems"
else
    echo "❌ Error: Failed to create ADF disk"
    exit 1
fi