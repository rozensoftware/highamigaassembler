"""Macro collection and expansion helpers for codegen."""

import copy


class MacroExpander:
    def __init__(self, module, ast_module, normalize_expr):
        self.ast = ast_module
        self.normalize_expr = normalize_expr
        self.macros = self.build_macros(module, ast_module)

    @staticmethod
    def build_macros(module, ast_module):
        """Collect macro definitions from module. Returns dict: {name: MacroDef}."""
        macros = {}
        for item in module.items:
            if isinstance(item, ast_module.MacroDef):
                macros[item.name] = item
        return macros

    def expand_macro(self, macro, args, print_debug=False):
        """Expand a macro by substituting arguments into the macro body."""
        expanded = []

        substitutions = {}
        for i, param_name in enumerate(macro.params):
            if i < len(args):
                substitutions[param_name] = args[i]

        if print_debug:
            print(f"DEBUG: Expanding macro '{macro.name}' with substitutions: {substitutions}")

        for stmt in macro.body:
            expanded_stmt = self.substitute_in_stmt(stmt, substitutions, print_debug=print_debug)
            if print_debug:
                print(f"DEBUG: Expanded statement: {expanded_stmt}")
            expanded.append(expanded_stmt)

        return expanded

    def substitute_in_stmt(self, stmt, substitutions, print_debug=False):
        """Recursively substitute macro parameters in statements."""
        stmt = copy.deepcopy(stmt)

        if print_debug:
            print(f"DEBUG: Substituting in stmt type={type(stmt).__name__}, target={getattr(stmt, 'target', None)}")
            print(f"DEBUG: Substitutions map: {substitutions}")

        ast = self.ast

        if isinstance(stmt, ast.Assign):
            if isinstance(stmt.target, str) and stmt.target in substitutions:
                if print_debug:
                    print(f"DEBUG: Target '{stmt.target}' is in substitutions")
                sub_val = substitutions[stmt.target]
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                    if print_debug:
                        print(f"DEBUG: Substituted target to VarRef.name: {stmt.target}")
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                    if print_debug:
                        print(f"DEBUG: Substituted target to string: {stmt.target}")
                else:
                    stmt.target = self.substitute_in_expr(sub_val, substitutions)
                    if print_debug:
                        print(f"DEBUG: Substituted target to expression: {stmt.target}")
            elif isinstance(stmt.target, ast.VarRef) and getattr(stmt.target, "name", None) in substitutions:
                sub_val = substitutions[getattr(stmt.target, "name")]
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                else:
                    stmt.target = self.substitute_in_expr(sub_val, substitutions)
            elif isinstance(stmt.target, ast.ArrayAccess):
                stmt.target = self.substitute_in_expr(stmt.target, substitutions)
            elif isinstance(stmt.target, ast.MemberAccess):
                stmt.target = self.substitute_in_expr(stmt.target, substitutions)

            stmt.expr = self.substitute_in_expr(stmt.expr, substitutions)

        elif isinstance(stmt, ast.CompoundAssign):
            if isinstance(stmt.target, str) and stmt.target in substitutions:
                sub_val = substitutions[stmt.target]
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                else:
                    stmt.target = self.substitute_in_expr(sub_val, substitutions)
            elif isinstance(stmt.target, ast.VarRef) and getattr(stmt.target, "name", None) in substitutions:
                sub_val = substitutions[getattr(stmt.target, "name")]
                if isinstance(sub_val, ast.VarRef):
                    stmt.target = sub_val.name
                elif isinstance(sub_val, str):
                    stmt.target = sub_val
                else:
                    stmt.target = self.substitute_in_expr(sub_val, substitutions)
            stmt.expr = self.substitute_in_expr(stmt.expr, substitutions)

        elif isinstance(stmt, ast.VarDecl):
            if stmt.init_expr:
                stmt.init_expr = self.substitute_in_expr(stmt.init_expr, substitutions)

        elif isinstance(stmt, ast.Return):
            if stmt.expr:
                stmt.expr = self.substitute_in_expr(stmt.expr, substitutions)

        elif isinstance(stmt, ast.If):
            stmt.cond = self.substitute_in_expr(stmt.cond, substitutions)
            stmt.then_body = [self.substitute_in_stmt(s, substitutions) for s in stmt.then_body]
            if stmt.else_body:
                stmt.else_body = [self.substitute_in_stmt(s, substitutions) for s in stmt.else_body]

        elif isinstance(stmt, ast.While):
            stmt.cond = self.substitute_in_expr(stmt.cond, substitutions)
            stmt.body = [self.substitute_in_stmt(s, substitutions) for s in stmt.body]

        elif isinstance(stmt, ast.DoWhile):
            stmt.cond = self.substitute_in_expr(stmt.cond, substitutions)
            stmt.body = [self.substitute_in_stmt(s, substitutions) for s in stmt.body]

        elif isinstance(stmt, ast.ForLoop):
            stmt.start = self.substitute_in_expr(stmt.start, substitutions)
            stmt.end = self.substitute_in_expr(stmt.end, substitutions)
            stmt.step = self.substitute_in_expr(stmt.step, substitutions)
            stmt.body = [self.substitute_in_stmt(s, substitutions) for s in stmt.body]

        elif isinstance(stmt, ast.RepeatLoop):
            stmt.count = self.substitute_in_expr(stmt.count, substitutions)
            stmt.body = [self.substitute_in_stmt(s, substitutions) for s in stmt.body]

        elif isinstance(stmt, ast.ExprStmt):
            stmt.expr = self.substitute_in_expr(stmt.expr, substitutions)

        elif isinstance(stmt, ast.CallStmt):
            if stmt.args:
                stmt.args = [self.substitute_in_expr(arg, substitutions) for arg in stmt.args]

        elif isinstance(stmt, ast.MacroCall):
            if stmt.args:
                stmt.args = [self.substitute_in_expr(arg, substitutions) for arg in stmt.args]

        return stmt

    def substitute_in_expr(self, expr, substitutions):
        """Recursively substitute macro parameters in expressions."""
        ast = self.ast
        if expr is None:
            return None

        expr = self.normalize_expr(expr)
        expr = copy.deepcopy(expr)

        if isinstance(expr, ast.VarRef):
            if expr.name in substitutions:
                return copy.deepcopy(substitutions[expr.name])
            return expr

        if isinstance(expr, ast.BinOp):
            expr.left = self.substitute_in_expr(expr.left, substitutions)
            expr.right = self.substitute_in_expr(expr.right, substitutions)
            return expr

        if isinstance(expr, ast.UnaryOp):
            expr.operand = self.substitute_in_expr(expr.operand, substitutions)
            return expr

        if isinstance(expr, ast.Call):
            if expr.args:
                expr.args = [self.substitute_in_expr(arg, substitutions) for arg in expr.args]
            return expr

        if isinstance(expr, ast.ArrayAccess):
            if expr.name in substitutions:
                sub = substitutions[expr.name]
                if isinstance(sub, ast.VarRef):
                    expr.name = sub.name
            if expr.indices:
                expr.indices = [self.substitute_in_expr(idx, substitutions) for idx in expr.indices]
            return expr

        if isinstance(expr, ast.MemberAccess):
            expr.base = self.substitute_in_expr(expr.base, substitutions)
            return expr

        if isinstance(expr, (ast.Number, ast.PreIncr, ast.PreDecr, ast.PostIncr, ast.PostDecr)):
            return expr

        return expr
