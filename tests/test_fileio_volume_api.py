"""Build and source contracts, not DOS runtime emulation, for volume helpers."""

import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from hasc.amiga_toolchain import (
    ToolchainError,
    resolve_vasm,
    resolve_vlink,
    select_lib_sources,
)


ROOT = Path(__file__).resolve().parents[1]
VOLUME_APIS = (
    "FileGetHardDriveVolume",
    "FileGetLaunchVolume",
    "FileSetLaunchDirectory",
)


@pytest.mark.parametrize("cpu", ["68000", "68020"])
def test_storage_demo_compiles_volume_calls(cpu, tmp_path):
    output = tmp_path / f"storage_volume_contract_{cpu}.s"
    result = subprocess.run(
        [sys.executable, "-m", "hasc.cli", "examples/storage_media_demo.has",
         "--cpu", cpu, "-o", str(output)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assembly = output.read_text(encoding="utf-8")
    for symbol in (*VOLUME_APIS, "WBGetLaunchDirectory"):
        assert re.search(rf"\bjsr\s+{symbol}\b", assembly), symbol


@pytest.mark.parametrize("symbol", VOLUME_APIS)
def test_volume_exports_select_fileio_and_dependencies(symbol):
    names = {path.name for path in select_lib_sources([symbol], ROOT / "lib")}
    assert names == {"fileio.s", "dos.s"}


def test_launch_directory_export_selects_workbench_library():
    names = {path.name for path in select_lib_sources(["WBGetLaunchDirectory"], ROOT / "lib")}
    assert names == {"wbstartup.s"}


@pytest.fixture
def vasm():
    try:
        return resolve_vasm()
    except ToolchainError as error:
        pytest.skip(str(error))


@pytest.mark.parametrize("cpu", ["68000", "68020"])
@pytest.mark.parametrize("example", ["storage_media_demo", "fileio_demo"])
def test_volume_examples_assemble_and_link(cpu, example, tmp_path, vasm):
    try:
        resolve_vlink()
    except ToolchainError as error:
        pytest.skip(str(error))
    output = tmp_path / f"storage_volume_{example}_{cpu}.s"
    executable = output.with_suffix(".exe")
    result = subprocess.run(
        [sys.executable, "-m", "hasc.cli", f"examples/{example}.has",
         "--cpu", cpu, "-o", str(output), "--exe", str(executable)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert executable.read_bytes()[:4] == bytes.fromhex("000003f3")
    assert executable.stat().st_size > 100


LOCAL_CONSTANTS = {
    "LIB_VERSION": 20, "LN_TYPE": 8, "NT_PROCESS": 13,
    "MEMF_PUBLIC": 1, "MEMF_CLEAR": 0x10000, "IOERR_NOCMD": -3,
    "ACCESS_READ": -2, "ERROR_OBJECT_NOT_FOUND": 205,
    "ERROR_DEVICE_NOT_MOUNTED": 218, "ERROR_NOT_A_DOS_DISK": 225,
    "ERROR_NO_DISK": 226, "ID_SIZEOF": 36, "ID_VOLUMENODE": 28,
    "FSSM_SIZEOF": 16, "FSSM_UNIT": 0, "FSSM_DEVICE": 4,
    "FSSM_ENVIRON": 8, "FSSM_FLAGS": 12, "DE_TABLESIZE": 0, "DE_SIZEBLOCK": 4,
    "IO_COMMAND": 28, "IO_FLAGS": 30, "IO_ERROR": 31, "IO_ACTUAL": 32,
    "IO_LENGTH": 36, "IO_DATA": 40, "IO_OFFSET": 44, "IOTD_SIZE": 56,
    "TD_GETGEOMETRY": 22, "DG_SECTORSIZE": 0, "DG_TOTALSECTORS": 4,
    "DG_DEVICETYPE": 28, "DG_FLAGS": 29, "DG_SIZEOF": 32,
    "DG_DIRECT_ACCESS": 0, "DG_COMMUNICATION": 9, "DG_UNKNOWN": 31,
    "DGB_REMOVABLE": 0, "DGF_REMOVABLE": 1,
    "DOS_LVO_INFO": -114, "DOS_LVO_GETPROGRAMDIR": -600,
    "DOS_LVO_LOCKDOSLIST": -654, "DOS_LVO_UNLOCKDOSLIST": -660,
    "DOS_LVO_FINDDOSENTRY": -684, "DOS_LVO_NEXTDOSENTRY": -690,
}
NDK_ALIASES = {
    "ID_SIZEOF": "id_SIZEOF", "ID_VOLUMENODE": "id_VolumeNode",
    "FSSM_SIZEOF": "FileSysStartupMsg_SIZEOF",
    "FSSM_UNIT": "fssm_Unit", "FSSM_DEVICE": "fssm_Device",
    "FSSM_ENVIRON": "fssm_Environ", "FSSM_FLAGS": "fssm_Flags",
    "DE_TABLESIZE": "de_TableSize", "DE_SIZEBLOCK": "de_SizeBlock",
    "DG_SECTORSIZE": "dg_SectorSize", "DG_TOTALSECTORS": "dg_TotalSectors",
    "DG_DEVICETYPE": "dg_DeviceType", "DG_FLAGS": "dg_Flags",
    "DG_SIZEOF": "dg_SIZEOF",
    "DOS_LVO_INFO": "_LVOInfo", "DOS_LVO_GETPROGRAMDIR": "_LVOGetProgramDir",
    "DOS_LVO_LOCKDOSLIST": "_LVOLockDosList",
    "DOS_LVO_UNLOCKDOSLIST": "_LVOUnLockDosList",
    "DOS_LVO_FINDDOSENTRY": "_LVOFindDosEntry",
    "DOS_LVO_NEXTDOSENTRY": "_LVONextDosEntry",
}


def _assemble_constants(vasm, cpu, tmp_path, includes, symbols, include_dirs):
    source = tmp_path / f"storage_volume_constants_{cpu}.s"
    output = source.with_suffix(".bin")
    source.write_text(
        "".join(f'    include "{name}"\n' for name in includes)
        + "    section storage_volume_constants,data\n"
        + "".join(f"    dc.l {symbol}\n" for symbol in symbols), encoding="ascii",
    )
    command = [vasm, f"-m{cpu}", "-Fbin", "-devpac"]
    for directory in include_dirs:
        command.extend(["-I", str(directory)])
    command.extend([str(source), "-o", str(output)])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return output.read_bytes()


@pytest.mark.parametrize("cpu", ["68000", "68020"])
def test_local_constants_assemble_to_pinned_ndk_values(cpu, tmp_path, vasm):
    actual = _assemble_constants(
        vasm, cpu, tmp_path, ["fileio.i"],
        [f"FILEIO_{name}" for name in LOCAL_CONSTANTS], [ROOT / "lib"],
    )
    expected = b"".join(struct.pack(">I", value & 0xFFFFFFFF)
                        for value in LOCAL_CONSTANTS.values())
    assert actual == expected


@pytest.mark.parametrize("cpu", ["68000", "68020"])
def test_local_constants_match_optional_ndk_headers(cpu, tmp_path, vasm):
    include = os.environ.get("NDK_INCLUDE")
    if not include:
        pytest.skip("Set NDK_INCLUDE to NDK Include_I for independent constant verification")
    ndk = Path(include)
    assert (ndk / "dos" / "dos.i").is_file(), f"Invalid NDK_INCLUDE: {ndk}"
    includes = [
        "fileio.i", "exec/libraries.i", "exec/nodes.i", "exec/memory.i",
        "exec/errors.i", "exec/io.i", "dos/dos.i", "dos/filehandler.i",
        "devices/trackdisk.i", "lvo/dos_lib.i",
    ]
    symbols = [symbol for name in LOCAL_CONSTANTS
               for symbol in (f"FILEIO_{name}", NDK_ALIASES.get(name, name))]
    actual = _assemble_constants(vasm, cpu, tmp_path, includes, symbols, [ROOT / "lib", ndk])
    assert len(actual) == len(LOCAL_CONSTANTS) * 8
    for name, (local, original) in zip(LOCAL_CONSTANTS, struct.iter_unpack(">II", actual)):
        assert local == original, f"FILEIO_{name}: {local:#x} != NDK {original:#x}"


def _fileio_block(start, end):
    source = (ROOT / "lib" / "fileio.s").read_text(encoding="utf-8")
    return source.split(f"\n{start}:", 1)[1].split(f"\n{end}:", 1)[0]


def test_source_contract_buffer_and_capacity_guards():
    block = _fileio_block("fileio_volume_buffer", "fileio_volume_suppress")
    assert re.search(r"move.l a2,d0\s+beq .invalid\s+tst.l d7\s+ble .invalid", block)
    assert block.index("clr.b (a2)") < block.index("tst.l fileio_dos_base")
    assert re.search(r"\.invalid:\s+moveq #-1,d0", block)
    root = _fileio_block("fileio_volume_root", "FileIoInit")
    assert re.search(r"addq.l #2,d0\s+cmp.l d7,d0\s+bhi .small", root)
    assert root.index("cmp.l d7,d0") < root.index(".publish:")
    assert "move.b #':',(a1)+\n    clr.b (a1)" in root
    assert re.search(r"\.small:\s+moveq #-2,d5", root)


def test_source_contract_legacy_gating_and_fixed_disk_filter():
    hard_drive = _fileio_block("FileGetHardDriveVolume", "fileio_volume_snapshot")
    gate = hard_drive[:hard_drive.index("bsr fileio_volume_suppress")]
    assert gate.count("cmpi.w #36,FILEIO_LIB_VERSION(a6)") == 2
    assert gate.count("blo .unsupported") == 2
    assert re.search(r"\.unsupported:\s+moveq #-3,d0", hard_drive)
    geometry = _fileio_block("fileio_volume_geometry", "FileSetLaunchDirectory")
    assert re.search(r"cmpi.b #FILEIO_DG_DIRECT_ACCESS,FILEIO_DG_DEVICETYPE\(a2\)"
                     r"\s+bne .close\s+btst #FILEIO_DGB_REMOVABLE,FILEIO_DG_FLAGS\(a2\)"
                     r"\s+bne .close\s+moveq #1,d3", geometry)
    assert re.search(r"\.unknown:\s+moveq #-3,d3", geometry)
    assert "cmpi.b #FILEIO_IOERR_NOCMD,FILEIO_IO_ERROR(a4)" in geometry


def test_source_contract_sys_preference_requires_geometry_and_identity():
    hard_drive = _fileio_block("FileGetHardDriveVolume", "fileio_volume_snapshot")
    assert re.search(r"bsr fileio_volume_geometry\s+cmpi.l #1,d0\s+beq .lock_path", hard_drive)
    assert re.search(r"bsr fileio_volume_identity\s+cmpi.l #1,d0\s+beq .qualifies", hard_drive)
    assert hard_drive.index(".qualifies:") < hard_drive.index(".prefer_sys:")
    identity = _fileio_block("fileio_volume_identity", "fileio_volume_same")
    assert "bsr fileio_volume_same" in identity
    same = _fileio_block("fileio_volume_same", "fileio_volume_geometry")
    assert "cmp.l FIV_FL_VOLUME(a0),d2" in same


def test_static_source_contract_snapshot_uses_populated_length_on_shrink():
    """Static guard only: no DOS-list mutation or runtime execution is exercised."""
    snapshot = _fileio_block("fileio_volume_snapshot", "fileio_volume_entry")
    assert re.search(r"\.copied:\s+moveq #FIV_LDF_DEVICES,d1"
                     r"\s+jsr FILEIO_DOS_LVO_UNLOCKDOSLIST\(a6\)"
                     r"\s+move.l a5,d0\s+move.l d6,d1"
                     r"\s+move.l a3,d2\s+sub.l a5,d2\s+bra .done", snapshot)
    assert re.search(r"\.done:\s+movem.l \(sp\)\+,d3-d7/a0-a6\s+rts", snapshot)
    caller = _fileio_block("FileGetHardDriveVolume", "fileio_volume_snapshot")
    assert re.search(r"bsr fileio_volume_snapshot\s+cmpi.l #-1,d0\s+beq .error"
                     r"\s+move.l d0,-12\(a5\)\s+move.l d1,-16\(a5\)"
                     r"\s+move.l d0,a4\s+move.l d2,d6"
                     r"\s+\.next:\s+tst.l d6\s+beq .selected", caller)
    assert re.search(r"\.advance:\s+adda.l #FIV_SIZE,a4"
                     r"\s+subi.l #FIV_SIZE,d6\s+bra .next", caller)
    assert re.search(r"move.l -16\(a5\),d0\s+move.l ExecBase,a6"
                     r"\s+jsr _LVOFreeMem\(a6\)", caller)


def test_static_source_contract_identity_allows_only_matching_live_task():
    """Static guard only: no handler startup or lock identity is emulated."""
    identity = _fileio_block("fileio_volume_identity", "fileio_volume_same")
    assert re.search(r"move.l d4,d0\s+moveq #20,d1\s+bsr fileio_volume_bptr"
                     r"\s+move.l a0,d0\s+beq .unlock"
                     r"\s+move.l FIV_TASK\(a5\),d0\s+bne .check_task"
                     r"\s+move.l FIV_FL_TASK\(a0\),d0\s+beq .unlock"
                     r"\s+move.l d0,FIV_TASK\(a5\)\s+\.check_task:"
                     r"\s+cmp.l FIV_FL_TASK\(a0\),d0\s+bne .unlock"
                     r"\s+\.next:", identity)
    assert re.search(r"bsr fileio_volume_entry\s+move.l a5,a0\s+move.l sp,a1"
                     r"\s+move.w #FIV_SIZE/4-1,d0\s+\.compare:"
                     r"\s+cmpm.l \(a0\)\+,\(a1\)\+\s+bne .next"
                     r"\s+dbra d0,.compare\s+moveq #1,d5", identity)
    assert identity.index(".check_task:") < identity.index(".compare:")
    assert identity.count("moveq #1,d5") == 1


def test_source_contract_launch_locks_are_borrowed():
    launch = _fileio_block("FileGetLaunchVolume", "fileio_volume_buffer")
    assert re.search(r"cmpi.w #36,FILEIO_LIB_VERSION\(a6\)\s+blo .registered"
                     r"\s+jsr FILEIO_DOS_LVO_GETPROGRAMDIR\(a6\)"
                     r"\s+tst.l d0\s+beq .registered", launch)
    assert "move.l fileio_launch_lock,a3" in launch
    assert "move.l d6,FIV_WINDOWPTR(a4)" in launch
    assert not re.search(r"\bjsr\s+\S*(?:UNLOCK|CURRENTDIR)", launch, re.IGNORECASE)
    setter = _fileio_block("FileSetLaunchDirectory", "FileGetLaunchVolume")
    assert re.search(r"move.l 8\(a6\),d0\s+move.l d0,fileio_launch_lock\s+moveq #0,d0", setter)


@pytest.mark.parametrize("array", ["LIB_SOURCES", "ORDERED_LIBS"])
def test_shell_builder_registers_fileio_in_both_arrays(array):
    script = (ROOT / "scripts" / "build_example.sh").read_text(encoding="utf-8")
    body = re.search(rf"^{array}=\(\n(.*?)^\)", script, re.MULTILINE | re.DOTALL)
    assert body, array
    assert '"$LIB_DIR/fileio.s"' in body.group(1)
