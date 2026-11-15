---
name: has-ptplayer-audio
description: >-
  Wire ProTracker MOD music and IFF 8SVX sound effects into HAS Amiga games via
  ptplayer. Use when adding music, SFX, PlayMusic/PlaySound, MOD/IFF assets,
  extract_8svx, #import music/sound, lib/audio.s, or linking the ptplayer library.
---

# HAS + ptplayer audio

**Prefer `#import music` / `#import sound` + `lib/audio.s`** for new code. The
manual `music_data.s` / `sounds_data.s` + inline `_mt_*` pattern remains valid
for existing games (Graveyard Shadows, astronautjetpac). Example
`examples/games/launchers` uses the preferred `#import` + `InitAudio` path.

## Preferred path (`#import` + `audio.s`)

```has
#import music "assets/title.mod" as mus_title;
#import sound "assets/laser.raw" as sfx_laser;
#import sound "assets/boom.iff" as sfx_boom vol=40 pri=120;

#include "../includes/audio_defs.has";

call InitAudio();
call PlayMusic(mus_title);     // mus_* are const track IDs
call PlaySound(sfx_laser);     // sfx_* are const table indices
call PauseMusic();
call ResumeMusic();
call ChangeMusic(mus_title);
call StopMusic();
call SetMusicVolume(16);
call QuitAudio();
```

| Piece | Role |
|---|---|
| `#import music` | CHIP `DATA_C` MOD fragment + entry in `music_table` |
| `#import sound` | CHIP sample (`dc.w 0` + PCM); `.iff`/`.8svx` via `tools/extract_8svx.py` |
| `build/gen/audio_tables.s` | Aggregated `music_table` / `sfx_table` (codegen) |
| `lib/audio.s` | HAS stack-ABI wrappers; auto-links `ptplayer.s` |
| `examples/includes/audio_defs.has` | `extern func` decls |

Sound defaults: `period=443` (~8 kHz PAL), `vol=32`, `pri=64`, `channel=-1`.
Regression: `examples/tests/compiler/import_audio_load_test.has`.

Lifecycle: call `InitAudio` + `PlayMusic` after successful gfx/asset init;
`QuitAudio` before `ReleaseSystem`.

## Legacy manual path (existing games)

| Piece | Role |
|---|---|
| `ptplayer` | HAS lib (`lib/ptplayer.s` + `ptplayer.i`); link in Makefile `LIBRARY_NAMES` |
| `assets/music_data.s` | `SECTION …,DATA_C`, `XDEF music`, `incbin` the `.mod` |
| `assets/sounds_data.s` | CHIP samples + `sfx_table` (`SfxStructure`-style: ptr, len words, period, vol, channel, pri) |
| `tools/extract_8svx.py` | IFF 8SVX → raw PCM (`make sfx`) |
| HAS procs | Hand-written `InitSound` / `PlayMusic` / `PlaySoundEffect` / `QuitSound` |

```has
native proc InitSound() -> void {
    asm {
        movem.l    d0/a0/a6,-(sp)
        lea        $DFF000,a6
        move.l     #0,a0          ; vectorBase
        moveq      #1,d0          ; PAL
        jsr        _mt_install_cia
        lea        $DFF000,a6
        move.b     #$01,d0        ; music owns channel 0
        jsr        _mt_musicmask
        movem.l    (sp)+,d0/a0/a6
    }
}

proc PlaySoundEffect(sfx_id: int) -> void {
    asm {
        movem.l    a6,-(sp)
        move.l     8(a6),d0
        clr.l      d1             ; no loop
        jsr        play_sfx
        movem.l    (sp)+,a6
    }
}
```

### Makefile checklist (legacy)

1. Add `ptplayer` to `LIBRARY_NAMES` (or rely on `audio.s` → `ptplayer.s` auto-dep).
2. `MUSIC_MOD` + rule: `music_data.o` depends on the `.mod`.
3. `SFX_NAMES` + `assets/sfx_%.raw: assets/%.iff` via `extract_8svx.py`.
4. `sounds_data.o` depends on all `SFX_RAW`.
5. Keep samples and MOD in **CHIP** (`DATA_C`).

Period for 8 kHz 8SVX: `≈ 3546895/8000 → 443`. Volume/priority per effect in `sfx_table`.

## SFX / track IDs

With `#import`, IDs are assigned in source order (separate counters for music
vs sound). With hand-built tables, define `const SFX_… = N` matching
`sfx_table` order.

## References

- Preferred API: [docs/LIBRARY_REFERENCE.md](../../../docs/LIBRARY_REFERENCE.md) (`audio.s`)
- Working preferred example: `examples/games/launchers`
- Working legacy games: `graveyardshadowsamiga`, `astronautjetpac/jetpac.has`
- Do not fight music channel 0; SFX use remaining Paula channels via `play_sfx`
