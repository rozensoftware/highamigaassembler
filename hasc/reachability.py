from dataclasses import dataclass
from typing import List, Set, Tuple

from . import ast


@dataclass
class StripReport:
    enabled: bool
    skipped_due_to_asm: bool
    roots: List[str]
    reachable: List[str]
    removed: List[str]


def _collect_internal_procs(module: ast.Module) -> Set[str]:
    procs: Set[str] = set()
    for item in module.items:
        if isinstance(item, ast.CodeSection):
            for code_item in item.items:
                if isinstance(code_item, ast.Proc):
                    procs.add(code_item.name)
    return procs


def _collect_direct_calls_from_expr(expr, out_calls: Set[str]) -> None:
    if expr is None:
        return

    if isinstance(expr, ast.Call):
        out_calls.add(expr.name)
        for arg in expr.args:
            _collect_direct_calls_from_expr(arg, out_calls)
        return

    if isinstance(expr, ast.BinOp):
        _collect_direct_calls_from_expr(expr.left, out_calls)
        _collect_direct_calls_from_expr(expr.right, out_calls)
        return

    if isinstance(expr, ast.UnaryOp):
        _collect_direct_calls_from_expr(expr.operand, out_calls)
        return

    if isinstance(expr, ast.ArrayAccess):
        for idx in expr.indices:
            _collect_direct_calls_from_expr(idx, out_calls)
        return

    if isinstance(expr, ast.MemberAccess):
        _collect_direct_calls_from_expr(expr.base, out_calls)
        return

    if isinstance(expr, ast.SetReg):
        _collect_direct_calls_from_expr(expr.value, out_calls)
        return

    # Prefix/postfix operators can wrap expressions with calls.
    if isinstance(expr, (ast.PreIncr, ast.PreDecr, ast.PostIncr, ast.PostDecr)):
        _collect_direct_calls_from_expr(expr.operand, out_calls)
        return


def _collect_direct_calls_from_stmt(stmt, out_calls: Set[str]) -> None:
    if isinstance(stmt, ast.CallStmt):
        out_calls.add(stmt.name)
        for arg in stmt.args:
            _collect_direct_calls_from_expr(arg, out_calls)
        return

    if isinstance(stmt, ast.MacroCall):
        # MacroCall can be either a macro expansion or an implicit function call.
        out_calls.add(stmt.name)
        for arg in stmt.args:
            _collect_direct_calls_from_expr(arg, out_calls)
        return

    if isinstance(stmt, ast.VarDecl):
        _collect_direct_calls_from_expr(stmt.init_expr, out_calls)
        return

    if isinstance(stmt, ast.Assign):
        _collect_direct_calls_from_expr(stmt.expr, out_calls)
        _collect_direct_calls_from_expr(stmt.target, out_calls)
        return

    if isinstance(stmt, ast.CompoundAssign):
        _collect_direct_calls_from_expr(stmt.expr, out_calls)
        return

    if isinstance(stmt, ast.Return):
        _collect_direct_calls_from_expr(stmt.expr, out_calls)
        return

    if isinstance(stmt, ast.ExprStmt):
        _collect_direct_calls_from_expr(stmt.expr, out_calls)
        return

    if isinstance(stmt, ast.If):
        _collect_direct_calls_from_expr(stmt.cond, out_calls)
        for s in stmt.then_body:
            _collect_direct_calls_from_stmt(s, out_calls)
        for s in (stmt.else_body or []):
            _collect_direct_calls_from_stmt(s, out_calls)
        return

    if isinstance(stmt, ast.While):
        _collect_direct_calls_from_expr(stmt.cond, out_calls)
        for s in stmt.body:
            _collect_direct_calls_from_stmt(s, out_calls)
        return

    if isinstance(stmt, ast.DoWhile):
        for s in stmt.body:
            _collect_direct_calls_from_stmt(s, out_calls)
        _collect_direct_calls_from_expr(stmt.cond, out_calls)
        return

    if isinstance(stmt, ast.ForLoop):
        _collect_direct_calls_from_expr(stmt.start, out_calls)
        _collect_direct_calls_from_expr(stmt.end, out_calls)
        _collect_direct_calls_from_expr(stmt.step, out_calls)
        for s in stmt.body:
            _collect_direct_calls_from_stmt(s, out_calls)
        return

    if isinstance(stmt, ast.RepeatLoop):
        _collect_direct_calls_from_expr(stmt.count, out_calls)
        for s in stmt.body:
            _collect_direct_calls_from_stmt(s, out_calls)
        return


def _build_call_graph(module: ast.Module, internal_procs: Set[str]) -> Tuple[dict, Set[str], bool]:
    graph = {name: set() for name in internal_procs}
    roots: Set[str] = set()
    has_top_level_asm = False

    for item in module.items:
        if not isinstance(item, ast.CodeSection):
            continue

        for code_item in item.items:
            if isinstance(code_item, ast.Proc):
                proc_calls: Set[str] = set()
                for stmt in code_item.body:
                    _collect_direct_calls_from_stmt(stmt, proc_calls)
                graph[code_item.name] = set(c for c in proc_calls if c in internal_procs)
            elif isinstance(code_item, ast.PublicDecl):
                if code_item.name in internal_procs:
                    roots.add(code_item.name)
            elif isinstance(code_item, ast.CallStmt):
                if code_item.name in internal_procs:
                    roots.add(code_item.name)
            elif isinstance(code_item, ast.MacroCall):
                if code_item.name in internal_procs:
                    roots.add(code_item.name)
            elif isinstance(code_item, ast.AsmBlock):
                has_top_level_asm = True

    return graph, roots, has_top_level_asm


def strip_unused_procs(module: ast.Module, enabled: bool = False):
    if not enabled:
        report = StripReport(
            enabled=False,
            skipped_due_to_asm=False,
            roots=[],
            reachable=[],
            removed=[],
        )
        return module, report

    internal_procs = _collect_internal_procs(module)
    if not internal_procs:
        report = StripReport(
            enabled=True,
            skipped_due_to_asm=False,
            roots=[],
            reachable=[],
            removed=[],
        )
        return module, report

    graph, roots, has_top_level_asm = _build_call_graph(module, internal_procs)

    # Conservative policy: top-level raw assembly can jump to internal procedures.
    # Also keep everything when no explicit roots were discovered.
    if has_top_level_asm or not roots:
        reachable = set(internal_procs)
    else:
        reachable: Set[str] = set()
        work = list(roots)
        while work:
            current = work.pop()
            if current in reachable:
                continue
            reachable.add(current)
            for callee in graph.get(current, set()):
                if callee not in reachable:
                    work.append(callee)

    removed = sorted(list(internal_procs - reachable))
    reachable_sorted = sorted(list(reachable))
    roots_sorted = sorted(list(roots))

    if not removed:
        report = StripReport(
            enabled=True,
            skipped_due_to_asm=has_top_level_asm,
            roots=roots_sorted,
            reachable=reachable_sorted,
            removed=[],
        )
        return module, report

    new_items = []
    for item in module.items:
        if not isinstance(item, ast.CodeSection):
            new_items.append(item)
            continue

        filtered = []
        for code_item in item.items:
            if isinstance(code_item, ast.Proc) and code_item.name in removed:
                continue
            filtered.append(code_item)

        new_items.append(ast.CodeSection(name=item.name, is_chip=item.is_chip, items=filtered))

    new_module = ast.Module(items=new_items)
    report = StripReport(
        enabled=True,
        skipped_due_to_asm=has_top_level_asm,
        roots=roots_sorted,
        reachable=reachable_sorted,
        removed=removed,
    )
    return new_module, report
