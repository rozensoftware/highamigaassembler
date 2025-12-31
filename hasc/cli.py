import argparse
import sys
import subprocess
from . import parser, codegen, validator
import os
from lark.exceptions import LarkError, UnexpectedInput, UnexpectedToken, UnexpectedCharacters


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hasc", description="High Assembler 68000 - prototype")
    ap.add_argument("input", help="Input .has file")
    ap.add_argument("-o", "--output", help="Output assembly file", default="out.s")
    ap.add_argument("--generate", help="Pre-process with Python script to generate code")
    ap.add_argument("--no-validate", action="store_true", help="Skip validation checks")
    args = ap.parse_args(argv)

    # If --generate specified, run Python script to generate HAS code
    if args.generate:
        try:
            print(f"Generating code with {args.generate}...", file=sys.stderr)
            result = subprocess.run(
                [sys.executable, args.generate],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                print(f"Error: Generation script failed with code {result.returncode}", file=sys.stderr)
                if result.stderr:
                    print(f"stderr: {result.stderr}", file=sys.stderr)
                sys.exit(1)
            src = result.stdout
            print(f"Generated {len(src)} bytes of HAS code", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print(f"Error: Generation script timed out (30 seconds)", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print(f"Error: Generation script not found: {args.generate}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: Failed to run generation script: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Normal case: read from input file
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                src = f.read()
        except FileNotFoundError:
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        except IOError as e:
            print(f"Error: Failed to read input file: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        base_dir = None
        if not args.generate:
            base_dir = os.path.dirname(os.path.abspath(args.input))
        mod = parser.parse(src, base_dir=base_dir)
    except SyntaxError as e:
        print(f"Error in {args.input}:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        sys.exit(1)
    except (UnexpectedToken, UnexpectedCharacters, UnexpectedInput) as e:
        print(f"Syntax error in {args.input}:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        sys.exit(1)
    except LarkError as e:
        print(f"Parse error in {args.input}:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        sys.exit(1)
    
    # Run validation unless disabled
    if not args.no_validate:
        try:
            val = validator.Validator(mod)
            warnings = val.validate()
            for warning in warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        except validator.ValidationError as e:
            print(f"Validation error in {args.input}:", file=sys.stderr)
            print(f"  {e}", file=sys.stderr)
            sys.exit(1)
    
    cg = codegen.CodeGen(mod)
    asm = cg.gen()

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(asm)

    print(f"Wrote assembly to {args.output}")


if __name__ == "__main__":
    main()
