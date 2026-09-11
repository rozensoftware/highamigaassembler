import argparse
import sys
import subprocess
from datetime import datetime
from collections import Counter
import os
from . import __version__, parser, codegen, validator
from . import ast
from . import reachability
from .target import CpuTarget, TargetSpec
from lark.exceptions import LarkError, UnexpectedInput, UnexpectedToken, UnexpectedCharacters

__author__ = "Piotr Rozentreter"


def _build_asm_preamble() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"; High Amiga Assembler (HAS) by Piotr Rozentreter (Rozsoft) Version: {__version__}\n"
        f"; Date: {timestamp}\n\n"
    )


def _count_ast_nodes(node, counter: Counter) -> None:
    if node is None:
        return
    if isinstance(node, list):
        for item in node:
            _count_ast_nodes(item, counter)
        return

    if isinstance(node, ast.Proc):
        counter["proc_count"] += 1
    elif isinstance(node, ast.FuncDecl):
        counter["func_decl_count"] += 1
    elif isinstance(node, ast.StructVarDecl):
        counter["struct_count"] += 1
    elif isinstance(node, ast.While):
        counter["while_count"] += 1
    elif isinstance(node, ast.DoWhile):
        counter["do_while_count"] += 1
    elif isinstance(node, ast.ForLoop):
        counter["for_loop_count"] += 1
    elif isinstance(node, ast.RepeatLoop):
        counter["repeat_loop_count"] += 1
    elif isinstance(node, ast.Loop):
        counter["loop_count"] += 1

    if not hasattr(node, "__dict__"):
        return

    for value in vars(node).values():
        if isinstance(value, list):
            for item in value:
                _count_ast_nodes(item, counter)
        elif hasattr(value, "__dict__"):
            _count_ast_nodes(value, counter)


def _build_asm_statistics(mod: ast.Module, asm_body: str) -> str:
    ast_counts = Counter()
    _count_ast_nodes(mod, ast_counts)

    lines = asm_body.splitlines()
    total_lines = len(lines)
    non_empty_lines = 0
    comment_lines = 0
    label_lines = 0
    directive_lines = 0
    instruction_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        non_empty_lines += 1
        if stripped.startswith(";"):
            comment_lines += 1
            continue
        if stripped.endswith(":"):
            label_lines += 1
            continue
        if stripped.startswith("."):
            directive_lines += 1
            continue
        instruction_lines += 1

    total_loops = (
        ast_counts["while_count"]
        + ast_counts["do_while_count"]
        + ast_counts["for_loop_count"]
        + ast_counts["repeat_loop_count"]
        + ast_counts["loop_count"]
    )

    return (
        "; --- HAS Build Statistics ---\n"
        f"; Source procedures: {ast_counts['proc_count']}\n"
        f"; Source declarations: {ast_counts['func_decl_count']}\n"
        f"; Source structures: {ast_counts['struct_count']}\n"
        f"; Source loops total: {total_loops} (while={ast_counts['while_count']}, do_while={ast_counts['do_while_count']}, for={ast_counts['for_loop_count']}, repeat={ast_counts['repeat_loop_count']}, loop={ast_counts['loop_count']})\n"
        f"; Assembly lines total: {total_lines}\n"
        f"; Assembly lines non-empty: {non_empty_lines}\n"
        f"; Assembly instructions: {instruction_lines}\n"
        f"; Assembly labels: {label_lines}\n"
        f"; Assembly directives: {directive_lines}\n"
        f"; Assembly comments: {comment_lines}\n"
        "; ----------------------------\n\n"
    )

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="hasc",
        description="High Assembler 68000 - prototype",
        epilog=f"Author: {__author__}"
    )
    ap.add_argument("input", help="Input .has file")
    ap.add_argument("-o", "--output", help="Output assembly file", default="out.s")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--generate", help="Pre-process with Python script to generate code")
    ap.add_argument("--no-validate", action="store_true", help="Skip validation checks")
    ap.add_argument(
        "--cpu",
        choices=[cpu.value for cpu in CpuTarget],
        default=CpuTarget.M68000.value,
        help="CPU target for code generation (default: 68000)",
    )
    ap.add_argument(
        "--strip-unused-procs",
        action="store_true",
        help="Remove unreachable internal procedures before code generation",
    )
    ap.add_argument(
        "--strip-unused-report",
        action="store_true",
        help="Print kept/removed procedure report (implies --strip-unused-procs)",
    )
    ap.add_argument(
        "--annotate",
        action="store_true",
        help="Emit HAS source-line and loop-end comments in generated assembly (debug aid, no effect on generated instructions)",
    )
    ap.add_argument(
        "--asm-stats",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include HAS Build Statistics comment block in output assembly (default: enabled)",
    )
    args = ap.parse_args(argv)
    target = TargetSpec.for_cpu(args.cpu)

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
    
    strip_enabled = args.strip_unused_procs or args.strip_unused_report
    mod, strip_report = reachability.strip_unused_procs(mod, enabled=strip_enabled)

    if args.strip_unused_report:
        if strip_report.skipped_due_to_asm:
            print(
                "Strip report: top-level asm block detected; keeping all internal procedures",
                file=sys.stderr,
            )
        roots = ", ".join(strip_report.roots) if strip_report.roots else "<none>"
        kept = ", ".join(strip_report.reachable) if strip_report.reachable else "<none>"
        removed = ", ".join(strip_report.removed) if strip_report.removed else "<none>"
        print(f"Strip report roots: {roots}", file=sys.stderr)
        print(f"Strip report kept: {kept}", file=sys.stderr)
        print(f"Strip report removed: {removed}", file=sys.stderr)

    cg = codegen.CodeGen(
        mod,
        target,
        node_lines=getattr(mod, "node_lines", None),
        source_lines=src.splitlines(),
        annotate=args.annotate,
    )
    try:
        asm = cg.gen()
    except codegen.CodeGenError as e:
        print(f"Code generation error in {args.input}:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        sys.exit(1)

    asm_output = _build_asm_preamble()
    if args.asm_stats:
        asm_output += _build_asm_statistics(mod, asm)
    asm_output += asm

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(asm_output)

    print(f"Wrote assembly to {args.output}")


if __name__ == "__main__":
    main()
