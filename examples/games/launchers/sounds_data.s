    INCLUDE "../../../lib/ptplayer.i"
    
; sound
SFX_PERIOD      equ 443              ; 8000 Hz
SFX_VOLUME      equ 32


; sound effects priorities (higher value -> higher priority)
SFX_PRI_LASER       equ 127
SFX_PRI_EXPLOSION   equ 126
SFX_PRI_HIT         equ 125

    SECTION    sounds,DATA_C

sfx_laser:       
    dc.w       0                             ; the first two bytes of sfx must be zero for using ptplayer lib
    incbin     "sfx_laser.raw"
    even
sfx_laser_len   EQU (*-sfx_laser)/2

sfx_explosion:       
    dc.w       0                             ; the first two bytes of sfx must be zero for using ptplayer lib
    incbin     "sfx_explosion.raw"
    even
sfx_explosion_len   EQU (*-sfx_explosion)/2

sfx_hit:       
    dc.w       0                             ; the first two bytes of sfx must be zero for using ptplayer lib
    incbin     "sfx_hit.raw"
    even
sfx_hit_len   EQU (*-sfx_hit)/2



    SECTION    sounds,CODE

    ; sound effects table
    xdef       sfx_table
sfx_table:
    ; 0 - laser sound effect
    dc.l       sfx_laser                     ; samples pointer
    dc.w       sfx_laser_len                 ; samples length (bytes)
    dc.w       SFX_PERIOD                    ; period
    dc.w       SFX_VOLUME                    ; volume
    dc.b       -1                            ; channel
    dc.b       SFX_PRI_LASER                 ; priority

    ; 1 - explosion sound effect
    dc.l       sfx_explosion                 ; samples pointer
    dc.w       sfx_explosion_len             ; samples length (bytes)
    dc.w       SFX_PERIOD                    ; period
    dc.w       SFX_VOLUME                    ; volume
    dc.b       -1                            ; channel
    dc.b       SFX_PRI_EXPLOSION             ; priority

    ; 2 - hit sound effect
    dc.l       sfx_hit                       ; samples pointer
    dc.w       sfx_hit_len                   ; samples length (bytes)
    dc.w       SFX_PERIOD                    ; period
    dc.w       SFX_VOLUME                    ; volume
    dc.b       -1                            ; channel
    dc.b       SFX_PRI_HIT                   ; priority