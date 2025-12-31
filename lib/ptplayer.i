    ifnd _SOUND_I
_SOUND_I	equ	1

; Sound effects structure, passed into _mt_playfx
		rsreset
sfx_ptr		rs.l	1
sfx_len		rs.w	1
sfx_per		rs.w	1
sfx_vol		rs.w	1
sfx_cha		rs.b	1
sfx_pri		rs.b	1
sfx_sizeof	rs.b	0

    endc