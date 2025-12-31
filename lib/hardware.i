    ifnd HARDWARE_I
HARDWARE_I = 1

    include "exec_lib.i"
    include "graphics_lib.i"

CUSTOM      EQU	$DFF000		; Custom chip base (absolute)
DMACON	    EQU	$096		; DMA control register (offset)
DMACONR	    EQU	$002		; DMA control read (offset)
BPLCON0	    EQU	$100		; Bitplane control 0
BPLCON1	    EQU	$102		; Bitplane control 1
BPLCON2	    EQU	$104		; Bitplane control 2
BPLCON3     EQU $106
BPLCON4     EQU $10c
BPL1MOD	    EQU	$108		; Bitplane 1 modulo
BPL2MOD	    EQU	$10A		; Bitplane 2 modulo
BLTAFWM     EQU $044
BLTALWM     EQU $046
DIWSTRT	    EQU	$08E		; Display window start
DIWSTOP	    EQU	$090		; Display window stop
DDFSTRT	    EQU	$092		; Data fetch start
DDFSTOP	    EQU	$094		; Data fetch stop
INTENA	    EQU	$09A		; Interrupt enable
INTENAR	    EQU	$01C		; Interrupt enable read
INTREQ      EQU $09C
INTREQR     EQU	$01E
COP1LCH	    EQU	$080		; Copper list 1 pointer high
COP1LCL	    EQU	$082		; Copper list 1 pointer low
COPJMP1	    EQU	$088		; Copper jump strobe 1
COP1LC      EQU $080



BLTCPT      EQU $048
BLTBPT      EQU $04C
BLTAPT      EQU $050
BLTDPT      EQU $054
BLTSIZE     EQU $058
BLTCMOD     EQU $060
BLTBMOD     EQU $062
BLTAMOD     EQU $064
BLTDMOD     EQU $066
BLTCON0     EQU $040
BLTCON1     EQU $042


JOY0DAT     EQU $00A
POTINP      EQU $016

ExecBase    EQU $4

CIAAPRA     EQU $bfe001
CIAAICR     EQU $bfed01
CIAASDR     EQU $bfec01
CIAACRA     EQU $bfee01
CIAA        EQU $bfe001
CIAB        EQU $bfd000
CIAPRA      EQU $000
CIATALO     EQU $400
CIATAHI     EQU $500
CIATBLO     EQU $600
CIATBHI     EQU $700
CIAICR      EQU $d00
CIACRA      EQU $e00
CIACRB      EQU $f00

FMODE       EQU $1fc
ADKCON      EQU $09E
ADKCONR     EQU $010

AUD         EQU	$0A0
AUD0	    EQU	$0A0
AUD1	    EQU	$0B0
AUD2	    EQU	$0C0
AUD3	    EQU	$0D0
AUD0LC      EQU AUD0
AUD0LCH     EQU AUD0
AUD0LCL     EQU AUD0+$02
AUD0LEN     EQU AUD0+$04
AUD0PER     EQU AUD0+$06
AUD0VOL     EQU AUD0+$08
AUD0DAT     EQU AUD0+$0A

AUD1LC      EQU AUD1
AUD1LCH     EQU AUD1
AUD1LCL     EQU AUD1+$02
AUD1LEN     EQU AUD1+$04
AUD1PER     EQU AUD1+$06
AUD1VOL     EQU AUD1+$08
AUD1DAT     EQU AUD1+$0A
AUD2LC      EQU AUD2
AUD2LCH     EQU AUD2
AUD2LCL     EQU AUD2+$02
AUD2LEN     EQU AUD2+$04
AUD2PER     EQU AUD2+$06
AUD2VOL     EQU AUD2+$08
AUD2DAT     EQU AUD2+$0A

AUD3LC      EQU AUD3
AUD3LCH     EQU AUD3
AUD3LCL     EQU AUD3+$02
AUD3LEN     EQU AUD3+$04
AUD3PER     EQU AUD3+$06
AUD3VOL     EQU AUD3+$08
AUD3DAT     EQU AUD3+$0A

; Custom chip registers (relative to $DFF000, assuming a5 = $DFF000)
SPR0PTH     EQU $120
SPR0PTL     EQU $122
SPR1PTH     EQU $124
SPR1PTL     EQU $126
SPR2PTH     EQU $128
SPR2PTL     EQU $12A
SPR3PTH     EQU $12C
SPR3PTL     EQU $12E
SPR4PTH     EQU $130
SPR4PTL     EQU $132
SPR5PTH     EQU $134
SPR5PTL     EQU $136
SPR6PTH     EQU $138
SPR6PTL     EQU $13A
SPR7PTH     EQU $13C
SPR7PTL     EQU $13E

; Bitplane pointer offsets
BPL1PTH	    EQU	$0E0		; Bitplane 1 pointer high
BPL1PTL	    EQU	$0E2		; Bitplane 1 pointer low
BPL2PTH	    EQU	$0E4		; Bitplane 2 pointer high
BPL2PTL	    EQU	$0E6		; Bitplane 2 pointer low
BPL3PTH	    EQU	$0E8		; Bitplane 3 pointer high
BPL3PTL	    EQU	$0EA		; Bitplane 3 pointer low
BPL4PTH	    EQU	$0EC		; Bitplane 4 pointer high
BPL4PTL	    EQU	$0EE		; Bitplane 4 pointer low
BPL5PTH	    EQU	$0F0		; Bitplane 5 pointer high
BPL5PTL	    EQU	$0F2		; Bitplane 5 pointer low
BPL6PTH	    EQU	$0F4		; Bitplane 6 pointer high
BPL6PTL	    EQU	$0F6		; Bitplane 6 pointer low

; Color registers (offsets)
COLOR0	    EQU	$180		; Color 0 (background)
COLOR1	    EQU	$182		; Color 1
COLOR2	    EQU	$184		; Color 2
COLOR3	    EQU	$186		; Color 3
COLOR4	    EQU	$188		; Color 4
COLOR5	    EQU	$18A		; Color 5
COLOR6	    EQU	$18C		; Color 6
COLOR7	    EQU	$18E		; Color 7
COLOR8	    EQU	$190		; Color 8
COLOR9	    EQU	$192		; Color 9
COLOR10	    EQU	$194		; Color 10
COLOR11	    EQU	$196		; Color 11
COLOR12	    EQU	$198		; Color 12
COLOR13	    EQU	$19A		; Color 13
COLOR14	    EQU	$19C		; Color 14
COLOR15	    EQU	$19E		; Color 15
COLOR16	    EQU	$1A0		; Color 16
COLOR17	    EQU	$1A2		; Color 17
COLOR18	    EQU	$1A4		; Color 18
COLOR19	    EQU	$1A6		; Color 19
COLOR20	    EQU	$1A8		; Color 20
COLOR21	    EQU	$1AA		; Color 21
COLOR22	    EQU	$1AC		; Color 22
COLOR23	    EQU	$1AE		; Color 23
COLOR24	    EQU	$1B0		; Color 24
COLOR25	    EQU	$1B2		; Color 25
COLOR26	    EQU	$1B4		; Color 26
COLOR27	    EQU	$1B6		; Color 27
COLOR28	    EQU	$1B8		; Color 28
COLOR29	    EQU	$1BA		; Color 29
COLOR30	    EQU	$1BC		; Color 30
COLOR31	    EQU	$1BE		; Color 31

VPOSR	    EQU	$004		; Vertical position read
VHPOSR	    EQU	$006		; Vertical/horizontal position


; Library call offsets
ExecSupervisor      EQU	-30
ExecForbid          EQU	-132
ExecPermit          EQU	-138
ExecFindTask        EQU	-294
ExecGetMsg          EQU	-372
ExecReplyMsg        EQU	-378
ExecWaitPort        EQU	-384
ExecOldOpenLib      EQU	-408
ExecCloseLib        EQU	-414

    endc
