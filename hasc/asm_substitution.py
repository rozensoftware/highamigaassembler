"""Inline asm @var substitution helpers for codegen."""

import re


def substitute_asm_vars(asm_content, params, locals_info, globals_map, extern_vars, frame_reg, fail):
    """Substitute @varname references in asm blocks with actual addresses/registers.

    Substitution rules:
    - @param_name: Register parameter -> register name; Stack parameter -> offset(frame_reg)
    - @local_var: -> -offset(frame_reg)
    - @global_var: -> label name

    Returns tuple of (substituted_content, comments) where comments document substitutions.
    """
    pattern = r"@([a-zA-Z_]\w*)"
    substitutions = []

    # Collect all matches first to avoid iterator issues during replacement.
    matches_list = list(re.finditer(pattern, asm_content))

    # Process substitutions in reverse order (to maintain string positions).
    for match in reversed(matches_list):
        var_name = match.group(1)
        start = match.start()
        end = match.end()

        # Check if it's a parameter (register or stack).
        param_obj = next((p for p in params if p.name == var_name), None)
        if param_obj:
            if param_obj.register and param_obj.register != "None":
                replacement = param_obj.register
                substitutions.insert(0, (var_name, replacement, "register parameter"))
            else:
                stack_params = [p for p in params if not (p.register and p.register != "None")]
                if param_obj in stack_params:
                    idx = stack_params.index(param_obj)
                    offset = 8 + 4 * idx
                    replacement = f"{offset}({frame_reg})"
                    substitutions.insert(0, (var_name, replacement, "stack parameter"))
                else:
                    asm_content = asm_content[:start] + f"???{var_name}???" + asm_content[end:]
                    continue
            asm_content = asm_content[:start] + replacement + asm_content[end:]
            continue

        # Check if it's a local variable.
        local_info = next((l for l in locals_info if l[0] == var_name), None)
        if local_info:
            _, _, offset = local_info
            replacement = f"-{offset}({frame_reg})"
            substitutions.insert(0, (var_name, replacement, "local variable"))
            asm_content = asm_content[:start] + replacement + asm_content[end:]
            continue

        # Check globals/externs.
        if var_name in globals_map:
            replacement = var_name
            substitutions.insert(0, (var_name, replacement, "global variable"))
            asm_content = asm_content[:start] + replacement + asm_content[end:]
        elif var_name in extern_vars:
            replacement = var_name
            substitutions.insert(0, (var_name, replacement, "external variable"))
            asm_content = asm_content[:start] + replacement + asm_content[end:]
        else:
            fail(f"Undefined symbol '{var_name}' in inline asm block")

    return asm_content, substitutions
