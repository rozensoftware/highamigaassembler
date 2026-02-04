#!/usr/bin/env python3
"""
Q16.16 Fixed-Point Helper
Converts decimal numbers to Q16.16 fixed-point integer format.

Q16.16 format uses 32 bits:
- Upper 16 bits: signed integer part
- Lower 16 bits: fractional part (0/65536 to 65535/65536)

Usage:
    python q16_helper.py 43.55
    python q16_helper.py -i 43 -f 55
    python q16_helper.py --list 1.5 2.75 -3.25 0.98
"""

import sys
import argparse


def q16_from_float(value: float) -> int:
    """Convert floating-point number to Q16.16 format."""
    return int(value * 65536)


def q16_from_parts(integer_part: int, fractional_part: int, decimal_places: int = 2) -> int:
    """
    Convert integer and fractional parts to Q16.16 format.
    
    Args:
        integer_part: Integer portion (e.g., 43 for 43.55)
        fractional_part: Fractional portion as integer (e.g., 55 for 0.55)
        decimal_places: Number of decimal places in fractional_part (default: 2)
    
    Returns:
        Q16.16 fixed-point value
    """
    divisor = 10 ** decimal_places
    frac_value = (fractional_part * 65536) // divisor
    
    if integer_part < 0:
        return (integer_part << 16) - frac_value
    else:
        return (integer_part << 16) + frac_value


def q16_to_float(q16_value: int) -> float:
    """Convert Q16.16 format to floating-point number."""
    return q16_value / 65536.0


def format_q16_constant(value: float, name: str = None) -> str:
    """Format a Q16.16 constant for HAS source code."""
    q16 = q16_from_float(value)
    if name:
        return f"const {name} = {q16};  // {value} in Q16.16"
    else:
        return f"{q16}  // {value}"


def main():
    parser = argparse.ArgumentParser(
        description='Convert decimal numbers to Q16.16 fixed-point format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 43.55                    # Output: 2854092  // 43.55
  %(prog)s -i 43 -f 55              # Output: 2854092  // From integer and fractional parts
  %(prog)s --list 1.5 2.75 3.14     # Convert multiple values
  %(prog)s --const SPEED 2.5        # Output: const SPEED = 163840;  // 2.5 in Q16.16
        """
    )
    
    parser.add_argument('value', nargs='?', type=float, 
                        help='Decimal value to convert (e.g., 43.55)')
    parser.add_argument('-i', '--integer', type=int,
                        help='Integer part (use with --fractional)')
    parser.add_argument('-f', '--fractional', type=int,
                        help='Fractional part (e.g., 55 for 0.55)')
    parser.add_argument('-d', '--decimal-places', type=int, default=2,
                        help='Number of decimal places in fractional part (default: 2)')
    parser.add_argument('-l', '--list', nargs='+', type=float,
                        help='Convert multiple values')
    parser.add_argument('-c', '--const', nargs=2, metavar=('NAME', 'VALUE'),
                        help='Generate HAS constant declaration')
    parser.add_argument('-r', '--reverse', type=int,
                        help='Convert Q16.16 value back to decimal')
    
    args = parser.parse_args()
    
    # Reverse conversion
    if args.reverse is not None:
        result = q16_to_float(args.reverse)
        print(f"{args.reverse} -> {result}")
        return
    
    # Constant declaration
    if args.const:
        name, value = args.const
        print(format_q16_constant(float(value), name))
        return
    
    # Multiple values
    if args.list:
        for val in args.list:
            q16 = q16_from_float(val)
            print(f"{q16:10d}  // {val}")
        return
    
    # Integer and fractional parts
    if args.integer is not None:
        if args.fractional is None:
            print("Error: --fractional required when using --integer")
            sys.exit(1)
        q16 = q16_from_parts(args.integer, args.fractional, args.decimal_places)
        decimal = q16_to_float(q16)
        print(f"{q16}  // {decimal}")
        return
    
    # Single value
    if args.value is not None:
        q16 = q16_from_float(args.value)
        print(f"{q16}  // {args.value}")
        return
    
    # No arguments - show help
    parser.print_help()
    print("\nQuick reference:")
    print("  0.25  -> 16384")
    print("  0.50  -> 32768")
    print("  0.75  -> 49152")
    print("  1.00  -> 65536")
    print("  2.00  -> 131072")


if __name__ == '__main__':
    main()
