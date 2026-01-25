#!/usr/bin/env python3
"""
Frame Merger - Combines multiple assembly frame files into a single file

Merges BOB/sprite assembly frame files (name*.s) into a single output file,
reducing file clutter and simplifying management.

Usage:
    python frame_merger.py 'pattern*.s' output.s
    python frame_merger.py 'bob_frame*.s' merged_bobs.s
    python frame_merger.py 'pattern*.s' output.s --leave-palette-label PAL_LABEL
"""
import sys
import glob
import argparse
from pathlib import Path
from typing import List, Tuple, Optional


def merge_assembly_frames(pattern: str, output_file: str, leave_palette_label: Optional[str] = None) -> None:
    """
    Merge multiple assembly frame files into a single output file.
    
    Args:
        pattern: Glob pattern to match input files (e.g., 'bob_frame*.s')
        output_file: Output filename
        leave_palette_label: If specified, only this palette's data will be copied.
                            Other palette labels will be kept but their data removed.
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
        in_palette_data = False
        current_palette_label = None
        skip_palette_data = False
        
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
                # Detect palette label (typically ends with _PAL or _Palette or similar)
                # and contains color data pattern
                stripped = line.strip()
                
                # Check if this is a palette label line (label with colon at start)
                if stripped and ':' in stripped and not stripped.startswith(';'):
                    # This might be a label
                    label_name = stripped.split(':')[0].strip()
                    
                    # Check if this is actually a palette label (contains 'palette' or 'pal' in name)
                    # and next lines contain palette data (DC.W with color values)
                    is_palette = False
                    if 'palette' in label_name.lower() or 'pal' in label_name.lower():
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            # Palette data typically starts with DC.W or dc.w
                            if next_line.upper().startswith('DC.W') or next_line.upper().startswith('DC.L'):
                                is_palette = True
                    
                    if is_palette:
                        in_palette_data = True
                        current_palette_label = label_name
                        
                        # Determine if we should skip this palette's data
                        if leave_palette_label and current_palette_label != leave_palette_label:
                            skip_palette_data = True
                            # Keep the label but skip data
                            output_lines.append(line)
                            print(f"  Keeping label but removing data for: {current_palette_label}")
                            continue
                        else:
                            skip_palette_data = False
                            if leave_palette_label and current_palette_label == leave_palette_label:
                                print(f"  Keeping palette data for: {current_palette_label}")
                
                # Check if we're leaving palette data section
                # (empty line or new label indicates end of palette data)
                if in_palette_data and (not stripped or (':' in stripped and not stripped.startswith(';'))):
                    if not stripped or (':' in stripped):
                        in_palette_data = False
                        skip_palette_data = False
                        current_palette_label = None
                
                # Skip palette data if needed
                if skip_palette_data and in_palette_data:
                    # Skip DC.W lines that are part of the palette
                    if stripped.upper().startswith('DC.W') or stripped.upper().startswith('DC.L'):
                        continue
                
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
    parser = argparse.ArgumentParser(
        description='Merge multiple assembly frame files into a single file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python frame_merger.py 'bob_frame*.s' merged_bobs.s
  python frame_merger.py 'sprite_frame*.s' all_sprites.s
  python frame_merger.py 'bob_*.s' output.s --leave-palette-label bob_0_Palette
        """
    )
    
    parser.add_argument('pattern', help="Glob pattern to match input files (e.g., 'bob_frame*.s')")
    parser.add_argument('output', help='Output filename')
    parser.add_argument('--leave-palette-label', metavar='LABEL',
                       help='Keep only this palette\'s data. Other palette labels will remain but their data will be removed.')
    
    args = parser.parse_args()
    
    try:
        merge_assembly_frames(args.pattern, args.output, args.leave_palette_label)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
