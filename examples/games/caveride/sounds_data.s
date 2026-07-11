; sounds_data.s — Stub SFX table for caveride
; TODO: Replace with real sound-effect data once audio assets are ready.
;
; ptplayer's play_sfx indexes into sfx_table by:
;   lea  sfx_table,a1
;   mulu #sfx_sizeof,d0   ; d0 = sfx_id
;   add.l d0,a1
; Each entry layout (from ptplayer.i, sfx_sizeof = 12):
;   sfx_ptr  .l  — pointer to sample in Chip RAM
;   sfx_len  .w  — sample length in words
;   sfx_per  .w  — hardware replay period
;   sfx_vol  .w  — volume 0..64
;   sfx_cha  .b  — channel (0-3 or -1 for auto)
;   sfx_pri  .b  — priority (must be non-zero)
;
; This stub defines one silent placeholder entry (id 0).
; Do NOT call play_sfx until this file is replaced with real data.

	include "../../../lib/ptplayer.i"

	SECTION sounds_data,DATA_C

	XDEF	sfx_table

sfx_table:
; --- SFX 0: placeholder (silent, channel auto, priority 1) ---
	DC.L	0		; sfx_ptr  — no sample data yet
	DC.W	1		; sfx_len  — 1 word (minimum valid length)
	DC.W	428		; sfx_per  — PAL period for middle C
	DC.W	0		; sfx_vol  — muted
	DC.B	-1		; sfx_cha  — auto-select channel
	DC.B	1		; sfx_pri  — non-zero required
