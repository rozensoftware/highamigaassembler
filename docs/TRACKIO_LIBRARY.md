# TrackIo Library (`lib/trackio.s`)

`lib/trackio.s` provides DOS-free floppy reads for takeover-mode games.
It reads raw tracks from `DF0:`, decodes sectors, and loads custom asset files
from a compact container stored in a custom ADF data disk.

## Why this library exists

During `TakeSystem()` takeover, calling `dos.library` is unsafe.
`trackio.s` uses direct hardware register access and no system calls.

## Safety model

- Call `TrackIoInit()` after takeover is active.
- Perform reads with `TrackIoReadSector` and `TrackIoReadFile`.
- Call `TrackIoDone()` before handing control back or exiting.
- The MFM DMA buffer (`trackio_encoded`) is in chip RAM (`BSS_C`); keep the
  trackio object linked into chip-capable memory on machines with fast/slow RAM.

## Include declarations

Use:

```has
#include "includes/trackio_defs.has";
```

## Runtime API

### `TrackIoInit() -> int`

Initializes DF0 access, homes the heads, spins up the motor, and resets the cache.

- Returns `0` on success.
- Returns `-1` on failure.

### `TrackIoDone() -> int`

Stops the motor, deselects drives, and marks the library uninitialized.

- Returns `0`.

### `TrackIoGetLastError() -> int`

Returns the last error code.

### `TrackIoGetFileSize(file_id: int) -> int`

Reads the container directory and returns file size in bytes for `file_id`.

- Returns `>= 0` on success (size in bytes).
- Returns negative error code on failure.

### `TrackIoReadSector(lba: int, dst: ptr) -> int`

Reads one logical 512-byte sector from the custom data disk.

- `lba`: `0..1759`
- `dst`: destination pointer (must hold 512 bytes)
- Returns `512` on success.
- Returns negative error code on failure.

### `TrackIoReadFile(file_id: int, dst: ptr, max_bytes: int) -> int`

Loads a complete custom file by numeric id.

- Returns number of bytes read on success.
- Returns negative error code on failure.

## Error codes

- `-1` not initialized
- `-2` invalid LBA
- `-3` sector not found after decode
- `-4` disk DMA timeout
- `-5` invalid container header
- `-6` file id not found
- `-7` destination buffer too small

`TrackIoGetFileSize` uses the same negative error model when it fails to read or
validate the directory.

## ADF container format expected by runtime

Logical sector 0 (`512` bytes):

- `u32 magic` = `'HAST'`
- `u16 version` = `1`
- `u16 entry_count` (`0..31`)
- directory entries (`16` bytes each):
  - `u32 file_id`
  - `u32 start_lba`
  - `u32 size_bytes`
  - `u16 flags` (`bit0 = XOR decode`)
  - `u8 xor_key`
  - `u8 reserved`

Asset payload starts at LBA `1`.

## Build the custom ADF

Use the included tool:

```bash
python tools/create_trackio_adf.py \
  --output disks/trackio_data.adf \
  --asset 1:assets/title.raw \
  --asset 2:assets/level1.map \
  --asset 3:assets/music.mod
```

Optional payload obfuscation:

```bash
python tools/create_trackio_adf.py \
  --output disks/trackio_data_xor.adf \
  --xor-key 0x5A \
  --asset 1:assets/title.raw
```

## In-game usage pattern

```has
#include "includes/trackio_defs.has";

code game:
    extern func TakeSystem() -> void;
    extern func ReleaseSystem() -> void;

    proc LoadAssets() -> int {
        var got: int;

        if (TrackIoInit() != 0) {
            return TrackIoGetLastError();
        }

        got = TrackIoGetFileSize(1);
        if (got < 0) {
          call TrackIoDone();
          return got;
        }
        if (got > TITLE_BUF_SIZE) {
          call TrackIoDone();
          return TRACKIO_ERR_DST_TOO_SMALL;
        }

        got = TrackIoReadFile(1, &title_buf, TITLE_BUF_SIZE);
        if (got < 0) {
            call TrackIoDone();
            return got;
        }

        got = TrackIoGetFileSize(2);
        if (got < 0) {
          call TrackIoDone();
          return got;
        }
        if (got > LEVEL_BUF_SIZE) {
          call TrackIoDone();
          return TRACKIO_ERR_DST_TOO_SMALL;
        }

        got = TrackIoReadFile(2, &level_buf, LEVEL_BUF_SIZE);
        if (got < 0) {
            call TrackIoDone();
            return got;
        }

        call TrackIoDone();
        return 0;
    }
```

## Important limitations

- Runtime only supports `DF0:` DD geometry (`1760` logical sectors).
- Container directory is limited to `31` assets.
- This is a custom loader format, not OFS/FFS filename parsing.
