"""Amiga host toolchain helpers: vasm → vlink → optional bootable ADF.

Used by ``hasc.cli`` for ``--exe`` / ``--adf``. Prefer assemble as ``-Fhunk``
object(s) then ``vlink -bamigahunk`` (same shape as ``scripts/build_example.sh``).

Library linking: when a parsed Module (or HAS source) declares ``extern`` symbols,
auto-select matching ``lib/*.s`` providers via ``xdef`` scan plus a small known
dependency closure. Programs with no externs link as a single object.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Union

from . import ast
from .target import CpuTarget, TargetSpec

__author__ = "Piotr Rozentreter"


class ToolchainError(RuntimeError):
    """Raised when assembler, linker, or ADF tooling fails or is missing."""


# Ordered lib sources used for deterministic link order (excludes font8x8_2.s
# which duplicates the ``fonts`` symbol from font8x8.s).
_DEFAULT_LIB_ORDER: Sequence[str] = (
    "debug.s",
    "helpers.s",
    "takeover.s",
    "graphics.s",
    "copper.s",
    "amiga_gfx.s",
    "font8x8.s",
    "input.s",
    "keyboard.s",
    "palette_fade.s",
    "sprite.s",
    "gui.s",
    "gui_keyboard.s",
    "str.s",
    "heap.s",
    "math.s",
    "bob.s",
    "bob_animation.s",
    "textbob.s",
    "tilemap.s",
    "ptplayer.s",
    "audio.s",
    "timer.s",
    "dos.s",
    "fileio.s",
    "trackio.s",
    "cpu.s",
    "gui_intuition.s",
    "wbstartup.s",
)

# Cross-lib dependencies mirroring scripts/build_example.sh.
_LIB_DEPS: Dict[str, Sequence[str]] = {
    "gui.s": ("gui_keyboard.s", "graphics.s", "input.s"),
    "gui_keyboard.s": ("gui.s", "keyboard.s"),
    # copper.s is required because SetGraphicsMode XREFs DetachCopperTail
    # (no-op when unused). copper.s in turn XREFs gfx_active_copper_end.
    "graphics.s": ("helpers.s", "sprite.s", "takeover.s", "copper.s"),
    "copper.s": ("graphics.s", "helpers.s"),
    "amiga_gfx.s": ("helpers.s",),
    "input.s": ("helpers.s",),
    "keyboard.s": ("takeover.s",),
    "heap.s": ("helpers.s",),
    "str.s": ("helpers.s",),
    "bob.s": ("graphics.s", "helpers.s", "heap.s"),
    "bob_animation.s": ("bob.s", "heap.s"),
    "textbob.s": ("bob.s", "graphics.s", "heap.s"),
    "tilemap.s": ("graphics.s",),
    "ptplayer.s": ("takeover.s",),
    "audio.s": ("ptplayer.s",),
    "fileio.s": ("dos.s",),
    "trackio.s": ("helpers.s",),
}

_XDEF_RE = re.compile(
    r"^\s*xdef\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.MULTILINE,
)
_EXTERN_SRC_RE = re.compile(
    r"^\s*extern\s+(?:func|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.MULTILINE,
)


def project_root_from(start: Optional[Union[str, Path]] = None) -> Path:
    """Walk parents looking for a HAS project root (has ``hasc/`` and ``lib/``)."""
    cur = Path(start or Path(__file__).resolve()).resolve()
    if cur.is_file():
        cur = cur.parent
    for candidate in (cur, *cur.parents):
        if (candidate / "hasc").is_dir() and (candidate / "lib").is_dir():
            return candidate
    # Fallback: package parent (hasc/..)
    return Path(__file__).resolve().parents[1]


def resolve_vasm() -> str:
    """Locate vasmm68k_mot / vasm68000_mot. Honors ``VASM`` env override."""
    env = os.environ.get("VASM")
    if env:
        path = Path(env)
        if path.is_file() or shutil.which(env):
            return str(path if path.is_file() else shutil.which(env))
        raise ToolchainError(
            f"VASM is set to {env!r} but that assembler was not found."
        )

    for name in ("vasmm68k_mot", "vasm68000_mot"):
        found = shutil.which(name)
        if found:
            return found

    raise ToolchainError(
        "Assembler not found (tried: vasmm68k_mot, vasm68000_mot). "
        "Install vasm or set VASM=/path/to/vasmm68k_mot."
    )


def resolve_vlink() -> str:
    """Locate vlink. Honors ``VLINK`` env override."""
    env = os.environ.get("VLINK")
    if env:
        path = Path(env)
        if path.is_file() or shutil.which(env):
            return str(path if path.is_file() else shutil.which(env))
        raise ToolchainError(
            f"VLINK is set to {env!r} but that linker was not found."
        )

    found = shutil.which("vlink")
    if found:
        return found

    raise ToolchainError(
        "Linker not found (tried: vlink). Install vlink or set VLINK=/path/to/vlink."
    )


def vasm_cpu_flag(cpu: Union[TargetSpec, CpuTarget, str]) -> str:
    """Return the vasm ``-m68000`` / ``-m68020`` flag for the given target."""
    if isinstance(cpu, TargetSpec):
        cpu_val = cpu.cpu.value
    elif isinstance(cpu, CpuTarget):
        cpu_val = cpu.value
    else:
        cpu_val = str(cpu)
    if cpu_val not in ("68000", "68020"):
        raise ToolchainError(f"Unsupported CPU for vasm: {cpu_val}")
    return f"-m{cpu_val}"


def collect_extern_names(mod: Optional[ast.Module]) -> Set[str]:
    """Collect ``extern`` symbol names from a parsed Module."""
    names: Set[str] = set()
    if mod is None:
        return names

    def walk(node) -> None:
        if node is None:
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, ast.ExternDecl):
            names.add(node.name)
            return
        if isinstance(node, ast.CodeSection):
            walk(node.items)
            return
        if isinstance(node, ast.Module):
            walk(node.items)

    walk(mod)
    return names


def collect_extern_names_from_source(source: str) -> Set[str]:
    """Fallback: scan HAS source text for ``extern func|var`` declarations."""
    return set(_EXTERN_SRC_RE.findall(source))


def _scan_xdefs(lib_path: Path) -> Set[str]:
    try:
        text = lib_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(_XDEF_RE.findall(text))


def build_xdef_index(lib_dir: Path) -> Dict[str, Path]:
    """Map exported symbol → first providing ``lib/*.s`` (ordered scan)."""
    index: Dict[str, Path] = {}
    for name in _DEFAULT_LIB_ORDER:
        path = lib_dir / name
        if not path.is_file():
            continue
        for sym in _scan_xdefs(path):
            index.setdefault(sym, path)
    # Also index any extra .s files present (except known duplicate font).
    for path in sorted(lib_dir.glob("*.s")):
        if path.name == "font8x8_2.s":
            continue
        if path.name in _DEFAULT_LIB_ORDER:
            continue
        for sym in _scan_xdefs(path):
            index.setdefault(sym, path)
    return index


def select_lib_sources(
    extern_symbols: Iterable[str],
    lib_dir: Path,
    *,
    xdef_index: Optional[Dict[str, Path]] = None,
) -> List[Path]:
    """Choose ``lib/*.s`` files needed for the given extern symbols.

    Applies a small dependency closure for common graphics/GUI stacks.
    Returns paths in deterministic link order.
    """
    lib_dir = lib_dir.resolve()
    index = xdef_index if xdef_index is not None else build_xdef_index(lib_dir)
    wanted: Set[str] = set()
    for sym in extern_symbols:
        provider = index.get(sym)
        if provider is not None:
            wanted.add(provider.name)

    changed = True
    while changed:
        changed = False
        for name in list(wanted):
            for dep in _LIB_DEPS.get(name, ()):
                if dep not in wanted and (lib_dir / dep).is_file():
                    wanted.add(dep)
                    changed = True

    ordered: List[Path] = []
    seen: Set[str] = set()
    for name in _DEFAULT_LIB_ORDER:
        if name in wanted and name not in seen:
            ordered.append(lib_dir / name)
            seen.add(name)
    # Any extra selected libs not in the default order.
    for name in sorted(wanted):
        if name not in seen:
            ordered.append(lib_dir / name)
            seen.add(name)
    return ordered


def _run_tool(cmd: Sequence[str], *, label: str) -> None:
    try:
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ToolchainError(f"{label} executable not found: {cmd[0]}") from exc

    if result.returncode != 0:
        parts = [f"{label} failed (exit {result.returncode}):"]
        parts.append("  command: " + " ".join(cmd))
        if result.stdout and result.stdout.strip():
            parts.append("  stdout:\n" + result.stdout.rstrip())
        if result.stderr and result.stderr.strip():
            parts.append("  stderr:\n" + result.stderr.rstrip())
        raise ToolchainError("\n".join(parts))


def assemble_object(
    asm_path: Union[str, Path],
    obj_path: Union[str, Path],
    *,
    cpu: Union[TargetSpec, CpuTarget, str],
    include_dirs: Optional[Sequence[Union[str, Path]]] = None,
    vasm: Optional[str] = None,
) -> Path:
    """Assemble one ``.s`` file to a hunk object (``-Fhunk``)."""
    asm_path = Path(asm_path)
    obj_path = Path(obj_path)
    obj_path.parent.mkdir(parents=True, exist_ok=True)

    vasm_bin = vasm or resolve_vasm()
    cmd: List[str] = [
        vasm_bin,
        vasm_cpu_flag(cpu),
        "-Fhunk",
        "-devpac",
        "-opt-allbra",
    ]
    for inc in include_dirs or ():
        cmd.extend(["-I", str(inc)])
    cmd.extend([str(asm_path), "-o", str(obj_path)])
    _run_tool(cmd, label="vasm")
    return obj_path


def link_hunk_exe(
    objects: Sequence[Union[str, Path]],
    exe_path: Union[str, Path],
    *,
    vlink: Optional[str] = None,
) -> Path:
    """Link hunk objects into an Amiga hunk executable."""
    exe_path = Path(exe_path)
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    vlink_bin = vlink or resolve_vlink()
    cmd: List[str] = [vlink_bin, "-bamigahunk", *[str(p) for p in objects], "-o", str(exe_path)]
    _run_tool(cmd, label="vlink")
    if not exe_path.is_file() or exe_path.stat().st_size == 0:
        raise ToolchainError(f"vlink produced no executable at {exe_path}")
    return exe_path


def build_exe_from_asm(
    asm_path: Union[str, Path],
    exe_path: Union[str, Path],
    *,
    cpu: Union[TargetSpec, CpuTarget, str],
    extern_symbols: Optional[Iterable[str]] = None,
    lib_dir: Optional[Union[str, Path]] = None,
    work_dir: Optional[Union[str, Path]] = None,
    keep_objects: bool = False,
) -> Path:
    """Assemble program (+ optional auto-selected libs) and link to ``exe_path``."""
    asm_path = Path(asm_path).resolve()
    exe_path = Path(exe_path)
    root = project_root_from(asm_path)
    lib_path = Path(lib_dir) if lib_dir else (root / "lib")
    if not lib_path.is_dir():
        lib_path = root / "lib"

    symbols = set(extern_symbols or ())
    lib_sources = select_lib_sources(symbols, lib_path) if symbols else []

    cleanup_dirs: List[Path] = []
    if work_dir is not None:
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="hasc_build_"))
        cleanup_dirs.append(work)

    try:
        include_dirs = [lib_path] if lib_path.is_dir() else []
        # Also allow INCLUDEs relative to the asm file directory.
        include_dirs.append(asm_path.parent)

        prog_obj = work / (asm_path.stem + ".o")
        assemble_object(
            asm_path,
            prog_obj,
            cpu=cpu,
            include_dirs=include_dirs,
        )

        objects: List[Path] = [prog_obj]
        for lib_src in lib_sources:
            lib_obj = work / (lib_src.stem + ".o")
            assemble_object(
                lib_src,
                lib_obj,
                cpu=cpu,
                include_dirs=include_dirs,
            )
            objects.append(lib_obj)

        try:
            return link_hunk_exe(objects, exe_path)
        except ToolchainError as exc:
            # Surface unknown externs when link fails for clearer diagnostics.
            if symbols:
                index = build_xdef_index(lib_path)
                unknown = sorted(s for s in symbols if s not in index)
                if unknown:
                    raise ToolchainError(
                        f"{exc}\n"
                        f"Note: no lib/ xdef provider found for: {', '.join(unknown)}. "
                        "Add the providing .s under lib/ or link extra objects manually."
                    ) from exc
            raise
    finally:
        if not keep_objects:
            for d in cleanup_dirs:
                shutil.rmtree(d, ignore_errors=True)


def resolve_xdftool_cmd(python: Optional[str] = None) -> List[str]:
    """Resolve xdftool invocation: ``XDFTOOL``, PATH ``xdftool``, or amitools module."""
    env = os.environ.get("XDFTOOL")
    if env:
        # Allow quoted multi-word overrides via simple split.
        return env.split()

    found = shutil.which("xdftool")
    if found:
        return [found]

    py = python or sys.executable
    try:
        probe = subprocess.run(
            [
                py,
                "-c",
                "import importlib.util, sys; "
                "sys.exit(0 if importlib.util.find_spec('amitools.tools.xdftool') else 1)",
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ToolchainError(
            f"Python interpreter for amitools not found: {py}"
        ) from exc

    if probe.returncode == 0:
        return [py, "-m", "amitools.tools.xdftool"]

    raise ToolchainError(
        "xdftool / amitools not found. Install amitools in the project venv "
        "('.venv/bin/python3 -m pip install amitools') or set XDFTOOL=/path/to/xdftool."
    )


def create_bootable_adf(
    adf_path: Union[str, Path],
    exe_path: Union[str, Path],
    *,
    volume_name: Optional[str] = None,
    python: Optional[str] = None,
) -> Path:
    """Create a bootable ADF with the program and ``S/startup-sequence``."""
    adf_path = Path(adf_path)
    exe_path = Path(exe_path)
    if not exe_path.is_file():
        raise ToolchainError(f"Executable not found for ADF: {exe_path}")

    adf_path.parent.mkdir(parents=True, exist_ok=True)
    if adf_path.exists():
        adf_path.unlink()

    vol = volume_name or adf_path.stem
    prog_name = exe_path.name
    xdf = resolve_xdftool_cmd(python=python)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix="_startup-sequence",
        delete=False,
    ) as startup:
        startup.write(
            "; Auto-generated startup-sequence\n"
            f'echo "Starting {prog_name}..."\n'
            f"SYS:{prog_name}\n"
            "endcli >NIL:\n"
        )
        startup_path = Path(startup.name)

    try:
        cmd = [
            *xdf,
            str(adf_path),
            "create",
            "+",
            "format",
            vol,
            "+",
            "makedir",
            "S",
            "+",
            "write",
            str(exe_path),
            prog_name,
            "+",
            "write",
            str(startup_path),
            "S/startup-sequence",
        ]
        _run_tool(cmd, label="xdftool")
    finally:
        try:
            startup_path.unlink(missing_ok=True)
        except OSError:
            pass

    if not adf_path.is_file() or adf_path.stat().st_size == 0:
        raise ToolchainError(f"ADF was not created at {adf_path}")
    return adf_path


def default_exe_path_for_adf(adf_path: Union[str, Path]) -> Path:
    """When ``--adf`` is given without ``--exe``, place exe next to the ADF."""
    adf = Path(adf_path)
    return adf.with_suffix(".exe")
