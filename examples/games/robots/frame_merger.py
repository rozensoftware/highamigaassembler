#!/usr/bin/env python3
"""
Frame Merger - Combines multiple assembly frame files into a single file

Merges BOB/sprite assembly frame files (name*.s) into a single output file,
reducing file clutter and simplifying management.

Usage:
    python frame_merger.py 'pattern*.s' output.s
    python frame_merger.py 'bob_frame*.s' merged_bobs.s
"""
import sys
import glob
from pathlib import Path
from typing import List, Tuple


def merge_assembly_frames(pattern: str, output_file: str) -> None:
    """
    Merge multiple assembly frame files into a single output file.
    
    Args:
        pattern: Glob pattern to match input files (e.g., 'bob_frame*.s')
        output_file: Output filename
    """
    # Find all matching files
    input_files = sorted(glob.glob(pattern))
    
    if not input_files:
        print(f"Error: No files matching pattern '{pattern}'")
        sys.exit(1)
    
    print(f"Found {len(input_files)} file(s) to merge:")
    for f in input_files:
        print(f"  - {f}")
    
    # Parse all files
    sections = []
    palette_data = []
    bob_data_sections = []
    xdef_labels = []
    
    for filepath in input_files:
        with open(filepath, 'r') as f:
            content = f.read()
            sections.append((filepath, content))
        
        # Extract XDEF labels for later reference
        for line in content.split('\n'):
            if 'XDEF' in line:
                # Extract all labels from XDEF line
                labels = line.split('XDEF')[1].strip()
                xdef_labels.extend([label.strip() for label in labels.split(',') if label.strip()])
    
    # Build merged output
    output_lines = []
    output_lines.append("; Auto-generated merged frame file")
    output_lines.append("; Merged from multiple frame files")
    output_lines.append("")
    output_lines.append("	SECTION bobs,DATA_C")
    
    # Collect all XDEF labels and add them
    if xdef_labels:
        xdef_str = ", ".join(xdef_labels)
        output_lines.append(f"	XDEF	{xdef_str}")
    
    output_lines.append("")
    
    # Extract and merge content from each file
    for filepath, content in sections:
        print(f"Processing: {filepath}")
        lines = content.split('\n')
        
        in_section = False
        skip_section_declaration = False
        skip_xdef = False
        
        for i, line in enumerate(lines):
            # Skip comments at the beginning
            if line.startswith(';') and not in_section:
                continue
            
            # Skip empty lines at the beginning
            if not line.strip() and not in_section:
                continue
            
            # Skip SECTION declaration (we'll use our own)
            if 'SECTION' in line:
                in_section = True
                skip_section_declaration = True
                continue
            
            # Skip XDEF (we've collected these already)
            if 'XDEF' in line:
                skip_xdef = True
                continue
            
            # Skip the first empty line after SECTION/XDEF
            if skip_section_declaration or skip_xdef:
                if not line.strip():
                    skip_section_declaration = False
                    skip_xdef = False
                    continue
            
            if in_section:
                output_lines.append(line)
        
        output_lines.append("")
    
    # Write merged file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(output_lines))
    
    print(f"\nMerged {len(input_files)} file(s) into: {output_file}")
    print(f"Total lines: {len(output_lines)}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python frame_merger.py 'pattern*.s' output.s")
        print("\nExample:")
        print("  python frame_merger.py 'bob_frame*.s' merged_bobs.s")
        print("  python frame_merger.py 'sprite_frame*.s' all_sprites.s")
        sys.exit(1)
    
    pattern = sys.argv[1]
    output_file = sys.argv[2]
    
    try:
        merge_assembly_frames(pattern, output_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
