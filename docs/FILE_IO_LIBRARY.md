# File I/O Library (`lib/fileio.s`)

`lib/fileio.s` provides thin wrappers for AmigaDOS file operations so HAS programs can read and write files using normal `extern func` calls.

## Safety model with takeover

If your program uses `TakeSystem()`, do not call DOS APIs while takeover is active.

Safe pattern:

1. `ReleaseSystem()`
2. `FileIoInit()` and file operations
3. `FileIoDone()`
4. `TakeSystem()`

For screen feedback, keep it at example/game level (not inside `lib/fileio.s`):

1. Draw "Loading..." (or set a loading flag) while takeover rendering is active.
2. Call `ReleaseSystem()` and perform DOS I/O.
3. Call `TakeSystem()` and clear/update the loading marker.

See also the runtime example in [fileio_demo.has](../examples/fileio_demo.has).

Run volume queries while the OS is running, before `TakeSystem()` (or after
`ReleaseSystem()`). Successfully copied volume strings remain safe to read during
takeover; the queries themselves must not run then.

## Include declarations

Use:

```has
#include "includes/fileio_defs.has";
```

The [declarations include](../examples/includes/fileio_defs.has) provides constants
and `extern func` declarations for all fileio exports. Workbench helpers are
declared separately as shown below.

Key constants:

- `DOS_MODE_READWRITE = 1004`
- `DOS_MODE_OLDFILE = 1005`
- `DOS_MODE_NEWFILE = 1006`
- `DOS_OFFSET_BEGINNING = -1`
- `DOS_OFFSET_CURRENT = 0`
- `DOS_OFFSET_END = 1`
- `DOS_SHARED_LOCK = -2`
- `DOS_EXCLUSIVE_LOCK = -1`

## API reference

### `FileIoInit() -> int`

Opens `dos.library` and caches its base.

- Returns `0` on success.
- Returns `-1` on failure.
- Idempotent: if already initialized, returns success without reopening.

### `FileIoDone() -> int`

Closes cached `dos.library` base if open.

- Returns `0`.
- Idempotent: safe to call even when not initialized.

### `FileIoErr() -> int`

Returns the DOS `IoErr()` code for the most recent failure.

- Returns DOS error code on success.
- Returns `-1` if `FileIoInit()` was not called.

Call this immediately after a failed `FileOpen`/`FileRead`/`FileWrite`/`FileSeek`/`FileClose` for best diagnostics.

### `FileOpen(path: ptr, mode: int) -> int`

Calls DOS `Open()`.

- `path`: pointer to NUL-terminated path string.
- `mode`: one of `DOS_MODE_READWRITE`, `DOS_MODE_OLDFILE`, `DOS_MODE_NEWFILE`.
- Returns file handle (BPTR) on success, `0` on failure.

### `FileClose(handle: int) -> int`

Calls DOS `Close()`.

- Returns DOS close result (non-zero for success in classic DOS style).

### `FileRead(handle: int, buffer: ptr, length: int) -> int`

Calls DOS `Read()`.

- Returns bytes read on success.
- Returns `-1` on failure.

### `FileWrite(handle: int, buffer: ptr, length: int) -> int`

Calls DOS `Write()`.

- Returns bytes written on success.
- Returns `-1` on failure.

### `FileSeek(handle: int, position: int, mode: int) -> int`

Calls DOS `Seek()`.

- `mode`: one of `DOS_OFFSET_BEGINNING`, `DOS_OFFSET_CURRENT`, `DOS_OFFSET_END`.
- Returns previous file position on success.
- Returns `-1` on failure.

### `FileDelete(path: ptr) -> int`

Calls DOS `DeleteFile()` style entry point.

- Returns `DOSTRUE` (`-1`) on success.
- Returns `DOSFALSE` (`0`) on failure.

### `FileRename(old_path: ptr, new_path: ptr) -> int`

Calls DOS `Rename()`.

- Returns `DOSTRUE` (`-1`) on success.
- Returns `DOSFALSE` (`0`) on failure.

### `FileLock(path: ptr, mode: int) -> int`

Calls DOS `Lock()`.

- `mode`: `DOS_SHARED_LOCK` or `DOS_EXCLUSIVE_LOCK`.
- Returns lock BPTR on success, `0` on failure.

### `FileUnLock(lock: int) -> void`

Calls DOS `UnLock()` to release a previously acquired lock.

### `FileExamine(lock: int, fib: ptr) -> int`

Calls DOS `Examine(lock, fib)`.

- Returns `DOSTRUE` (`-1`) on success.
- Returns `DOSFALSE` (`0`) on failure.
- `fib` must point to a valid DOS FileInfoBlock buffer.

### Volume query results

`FileGetHardDriveVolume` and `FileGetLaunchVolume` require successful
`FileIoInit()`. Both take a writable buffer and its capacity in bytes, including
space for the final colon and NUL terminator. On success they copy the actual
volume root, such as `Workbench:`, not a device name such as `DH0:` or an assign
such as `SYS:`. No partial result is published.

| Constant | Value | Meaning |
|----------|------:|---------|
| `FILE_VOLUME_OK` | `1` | Actual NUL-terminated `Volume:` root copied. |
| `FILE_VOLUME_UNAVAILABLE` | `0` | Volume unavailable, or no confirmed fixed device and no unknown classification/error. |
| `FILE_VOLUME_ERROR` | `-1` | Invalid arguments, DOS not initialized, or an operational error. |
| `FILE_VOLUME_TOO_SMALL` | `-2` | Buffer cannot hold the volume name, colon and NUL. |
| `FILE_VOLUME_UNSUPPORTED` | `-3` | Unsupported DOS/Exec version for HDD lookup, or unknown/unsupported device classification. |

For a non-null writable buffer with positive capacity, the first byte is cleared
before querying, so all non-success results leave an empty string. A null buffer
or nonpositive capacity returns `-1` without writing to the buffer.

### `FileGetHardDriveVolume(buffer: ptr, capacity: int) -> int`

Requires both `dos.library` and Exec V36 or newer; older systems return `-3`.
The selection policy is:

1. Prefer the volume currently resolved by `SYS:`, but only if a mounted,
	accessible device for that volume qualifies as fixed storage.
2. Otherwise use the first mounted, accessible qualifying device in DOS device
	enumeration order, not alphabetical order or a hard-coded `DH0:`.

Qualification requires successful `TD_GETGEOMETRY`, nonzero sector size and
sector count, device type `DG_DIRECT_ACCESS`, and no removable flag. Removable
media and other known nonqualifying device types are skipped. If no qualifying
volume is found, unknown/unsupported classification yields `-3` rather than `0`;
an operational error takes precedence as `-1`.

This is not detection of every physical HDD. Fixed block devices backed by CF
cards or emulators can qualify; drivers without usable geometry can remain
unknown. Interpretation of custom-handler startup data is a conservative
heuristic, not a guarantee of correct classification for every handler.
Because `SYS:` can be reassigned, the preferred volume is not necessarily the
system's physical boot device. Selection also does not guarantee writable save
storage; callers must handle failures when creating or writing files.

### `FileGetLaunchVolume(buffer: ptr, capacity: int) -> int`

Resolves the volume containing the program's launch directory:

1. On DOS V36+, use `GetProgramDir()` when it supplies a lock.
2. Otherwise use the borrowed lock registered by `FileSetLaunchDirectory()`.

There is no current-directory fallback. On AmigaOS 1.3, a Workbench launch can
provide the registered lock through `WBGetLaunchDirectory()` after `WBStartup()`.
A CLI launch on 1.3 has no automatic launch-directory information: without a
caller-supplied lock, the query returns `0` (unavailable), not a guessed volume.

### `FileSetLaunchDirectory(lock: int) -> int`

Registers a borrowed directory-lock BPTR as the launch-volume fallback; `0`
clears the registration. Always returns `0`. It neither duplicates nor unlocks
the lock. Keep the lock alive until registration is cleared. `FileIoDone()` does
not clear this registration.

### `WBGetLaunchDirectory() -> int` (`lib/wbstartup.s`)

Returns the borrowed directory-lock BPTR from the first Workbench startup
argument, or `0` when no argument is available (including CLI startup). Declare
the helper separately and link [lib/wbstartup.s](../lib/wbstartup.s) when using it:

```has
extern func WBGetLaunchDirectory() -> int;
```

Call it only after `WBStartup()` and before `WBExit()`. Never `FileUnLock()` this
Workbench-owned lock. Register it with
`FileSetLaunchDirectory(WBGetLaunchDirectory())` after startup, and call
`FileSetLaunchDirectory(0)` before `WBExit()` on every exit path, before Workbench
can release the lock. The libraries have no link dependency on each other.

See [storage_media_demo.has](../examples/storage_media_demo.has) for the complete
CLI/Workbench startup sequence, status reporting and cleanup, including the
expected `-1` result for a null output buffer. Run from CLI to see stdout.

## Build linkage

When assembling/linking a HAS program that uses these functions, include `lib/fileio.s` in your build alongside other used libraries.

The required storage constants are included in [lib/fileio.i](../lib/fileio.i),
verified against the Amiga NDK. Only the repository library include path is
needed; an external NDK installation is not required.

```bash
vasmm68k_mot -m68000 -Fhunk -Ilib lib/fileio.s -o build/fileio.o
```

The existing [demo build helper](../scripts/build_fileio_demo.sh) builds the file
I/O demo. The [generic example builder](../scripts/build_example.sh) also discovers
fileio exports and can build the storage-media example:

```bash
./scripts/build_example.sh examples/storage_media_demo.has
```

For manual linking, the storage-media example uses `lib/dos.s`, `lib/fileio.s`
and `lib/wbstartup.s`.

## Runtime test status

Musashi-based runtime coverage for this library is planned, but runtime automation remains pending while Musashi integration is still incomplete in this workspace.
