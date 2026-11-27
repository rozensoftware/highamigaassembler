"""Unit tests for hasc.amiga_toolchain argument/path logic (no vasm required).

Optional integration tests exercise ``hasc --exe`` / ``--adf`` when vasm, vlink,
and (for ADF) amitools are available on the host.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hasc import ast
from hasc.amiga_toolchain import (
    ToolchainError,
    collect_extern_names,
    collect_extern_names_from_source,
    default_exe_path_for_adf,
    project_root_from,
    resolve_vasm,
    resolve_vlink,
    resolve_xdftool_cmd,
    select_lib_sources,
    vasm_cpu_flag,
)
from hasc.target import CpuTarget, TargetSpec


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python3"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


def _toolchain_available() -> bool:
    try:
        resolve_vasm()
        resolve_vlink()
        return True
    except ToolchainError:
        return False


def _adf_toolchain_available() -> bool:
    if not _toolchain_available():
        return False
    try:
        resolve_xdftool_cmd(python=str(PYTHON))
        return True
    except ToolchainError:
        return False


requires_toolchain = pytest.mark.skipif(
    not _toolchain_available(),
    reason="vasm/vlink not available",
)
requires_adf = pytest.mark.skipif(
    not _adf_toolchain_available(),
    reason="vasm/vlink/amitools (xdftool) not available",
)


def test_vasm_cpu_flag_from_target_spec():
    assert vasm_cpu_flag(TargetSpec.for_cpu("68000")) == "-m68000"
    assert vasm_cpu_flag(TargetSpec.for_cpu("68020")) == "-m68020"
    assert vasm_cpu_flag(CpuTarget.M68000) == "-m68000"
    assert vasm_cpu_flag("68020") == "-m68020"


def test_vasm_cpu_flag_rejects_unknown():
    with pytest.raises(ToolchainError):
        vasm_cpu_flag("68040")


def test_default_exe_path_for_adf():
    assert default_exe_path_for_adf("/tmp/demo.adf") == Path("/tmp/demo.exe")
    assert default_exe_path_for_adf(Path("disks/game.adf")) == Path("disks/game.exe")


def test_project_root_from_package():
    assert project_root_from(ROOT / "hasc" / "cli.py") == ROOT
    assert (project_root_from() / "lib").is_dir()


def test_collect_extern_names_from_module():
    mod = ast.Module(
        items=[
            ast.ExternDecl(name="InitDOS", kind="func"),
            ast.CodeSection(
                name="main",
                is_chip=False,
                items=[ast.ExternDecl(name="PrintOut", kind="func")],
            ),
        ]
    )
    assert collect_extern_names(mod) == {"InitDOS", "PrintOut"}


def test_collect_extern_names_from_source():
    src = """
    extern func InitDOS() -> int;
    extern var foo: int;
    // not an extern: call InitDOS();
    """
    assert collect_extern_names_from_source(src) == {"InitDOS", "foo"}


def test_select_lib_sources_empty_when_no_externs():
    assert select_lib_sources([], ROOT / "lib") == []


def test_select_lib_sources_dos_and_deps():
    # InitDOS is provided by dos.s; fileio pulls dos via dep table when selected.
    libs = select_lib_sources(["InitDOS", "PrintOut"], ROOT / "lib")
    names = [p.name for p in libs]
    assert "dos.s" in names
    # Deterministic order: helpers before later libs if both present.
    if "helpers.s" in names and "dos.s" in names:
        assert names.index("helpers.s") < names.index("dos.s")


def test_select_lib_sources_gui_closure():
    # TakeSystem → takeover.s; bob APIs pull graphics/helpers/heap via closure.
    libs = select_lib_sources(["TakeSystem"], ROOT / "lib")
    names = [p.name for p in libs]
    assert "takeover.s" in names

    bob_libs = select_lib_sources(["BobAlloc"], ROOT / "lib")
    bob_names = {p.name for p in bob_libs}
    if "bob.s" in bob_names:
        assert "graphics.s" in bob_names
        assert "helpers.s" in bob_names
        assert "heap.s" in bob_names


@requires_toolchain
def test_cli_exe_builds_amiga_hunk(tmp_path: Path) -> None:
    src = ROOT / "examples" / "mintest.has"
    assert src.is_file()
    out_s = tmp_path / "mintest.s"
    out_exe = tmp_path / "mintest.exe"
    result = subprocess.run(
        [
            str(PYTHON),
            "-m",
            "hasc.cli",
            str(src),
            "-o",
            str(out_s),
            "--exe",
            str(out_exe),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_s.is_file()
    assert out_exe.is_file()
    assert out_exe.stat().st_size > 0
    # Amiga hunk executable magic (HUNK_HEADER = 0x000003F3)
    assert out_exe.read_bytes()[:4] == b"\x00\x00\x03\xf3"


@requires_toolchain
def test_cli_exe_68020_and_lib_link(tmp_path: Path) -> None:
    src = ROOT / "examples" / "dos_hello.has"
    assert src.is_file()
    out_s = tmp_path / "dos_hello.s"
    out_exe = tmp_path / "dos_hello.exe"
    result = subprocess.run(
        [
            str(PYTHON),
            "-m",
            "hasc.cli",
            str(src),
            "-o",
            str(out_s),
            "--cpu",
            "68020",
            "--exe",
            str(out_exe),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_exe.is_file()
    assert out_exe.stat().st_size > 100
    assert out_exe.read_bytes()[:4] == b"\x00\x00\x03\xf3"


@requires_adf
@pytest.mark.parametrize("cpu", ["68000", "68020"])
def test_cli_adf_bootable_disk(tmp_path: Path, cpu: str) -> None:
    src = ROOT / "examples" / "mintest.has"
    out_s = tmp_path / "mintest.s"
    out_adf = tmp_path / "mintest.adf"
    out_exe = tmp_path / "mintest.exe"
    result = subprocess.run(
        [
            str(PYTHON),
            "-m",
            "hasc.cli",
            str(src),
            "-o",
            str(out_s),
            "--cpu",
            cpu,
            "--exe",
            str(out_exe),
            "--adf",
            str(out_adf),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_adf.is_file()
    # Standard DD ADF size
    assert out_adf.stat().st_size == 901120
    boot_block = out_adf.read_bytes()[:1024]
    assert any(boot_block[12:])
    checksum = 0
    for offset in range(0, len(boot_block), 4):
        checksum += int.from_bytes(boot_block[offset:offset + 4], "big")
        checksum = (checksum & 0xFFFFFFFF) + (checksum >> 32)
    assert checksum == 0xFFFFFFFF
    list_cmd = resolve_xdftool_cmd(python=str(PYTHON)) + [str(out_adf), "list"]
    listed = subprocess.run(list_cmd, capture_output=True, text=True)
    assert listed.returncode == 0, listed.stderr
    assert "startup-sequence" in listed.stdout
    assert "mintest.exe" in listed.stdout
