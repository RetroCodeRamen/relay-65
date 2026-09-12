; Relay-65 Monitor ROM v0.1
; Assembled at $E000. UART at $C000 (data) / $C001 (status).

UART_DATA   = $C000
UART_STATUS = $C001
ROM_CTRL    = $C016
BOOT_JUMPER = $C017
IDE_DATA    = $C100
IDE_SECCNT  = $C102
IDE_LBA0    = $C103
IDE_LBA1    = $C104
IDE_LBA2    = $C105
IDE_LBA3    = $C106
IDE_CMD     = $C107
LINE        = $0200

INPTR       = $10
PTR         = $00
COUNT       = $02
DEST        = $04
LBA         = $06
SECCNT      = $08
PAGES       = $09

IRQVEC      = $00F0
NMIVEC      = $00F2

        .org $E000

reset:
        ldx #$FF
        txs
        cld
        lda #<rom_rti
        sta IRQVEC
        sta NMIVEC
        lda #>rom_rti
        sta IRQVEC+1
        sta NMIVEC+1
        cli
        jsr banner

prompt:
        lda #'>'
        jsr putc
        jsr getline
        jsr docmd
        jmp prompt

banner:
        ldx #0
bloop:
        lda hello,x
        beq bdone
        jsr putc
        inx
        jmp bloop
bdone:
        jsr maybe_boot
        rts

hello:
        .byte "Relay-65 monitor v0.1", $0A
        .byte "m addr   dump 16 bytes", $0A
        .byte ": addr bb [bb...]  deposit", $0A
        .byte "g addr   run", $0A
        .byte "f        boot FUZIX from CF", $0A, $00

putc:
        pha
pw:
        lda UART_STATUS
        and #$02
        beq pw
        pla
        sta UART_DATA
        rts

getc:
        lda UART_STATUS
        and #$01
        beq getc
        lda UART_DATA
        rts

getline:
        ldx #0
        stx INPTR
gl:
        jsr getc
        cmp #$0D
        beq glcr
        cmp #$0A
        beq glcr
        cmp #$08
        beq glbs
        cmp #$7F
        beq glbs
        sta LINE,x
        jsr putc
        inx
        jmp gl
glbs:
        cpx #0
        beq gl
        dex
        lda #$08
        jsr putc
        lda #' '
        jsr putc
        lda #$08
        jsr putc
        jmp gl
glcr:
        lda #0
        sta LINE,x
        lda #$0A
        jsr putc
        rts

docmd:
        ldx #0
        stx INPTR
        jsr skip
        ldx INPTR
        lda LINE,x
        beq cmdrts
        cmp #'m'
        beq cmd_m
        cmp #'M'
        beq cmd_m
        cmp #':'
        beq cmd_dep
        cmp #'g'
        beq cmd_g
        cmp #'G'
        beq cmd_g
        cmp #'f'
        beq cmd_f
        cmp #'F'
        beq cmd_f
        cmp #'?'
        beq cmd_help
        lda #'?'
        jsr putc
        lda #$0A
        jsr putc
cmdrts:
        rts

cmd_help:
        jsr banner
        rts

cmd_m:
        inc INPTR
        jsr parse_addr
        ldy #0
mdump:
        lda PTR+1
        jsr puthex
        lda PTR
        jsr puthex
        lda #':'
        jsr putc
        lda #' '
        jsr putc
md1:
        lda (PTR),y
        jsr puthex
        lda #' '
        jsr putc
        iny
        cpy #16
        bne md1
        lda #$0A
        jsr putc
        rts

cmd_dep:
        inc INPTR
        jsr parse_addr
        ldy #0
deploop:
        jsr skip
        ldx INPTR
        lda LINE,x
        beq depdone
        jsr parse_byte
        sta (PTR),y
        iny
        jmp deploop
depdone:
        rts

cmd_g:
        inc INPTR
        jsr parse_addr
        jmp (PTR)

cmd_f:
        jmp fuzix_boot

maybe_boot:
        lda BOOT_JUMPER
        lsr
        bcc noboot
        jsr fuzix_boot
noboot:
        rts

; IDE PIO: copy LBA 2–128 to $0200–$FFFF first so zp copy pointers survive,
; then LBA 1 bytes 0–255 into $0000–$00FF. Skip $0100–$01FF and $C000–$C2FF.
fuzix_boot:
        sei
        lda #0
        sta DEST
        lda #$02
        sta DEST+1
        lda #2
        sta LBA
        lda #0
        sta LBA+1
        lda #127
        sta SECCNT
nextsec:
        jsr readsec
        inc LBA
        bne lbaok
        inc LBA+1
lbaok:
        dec SECCNT
        bne nextsec
        lda #0
        sta DEST
        sta DEST+1
        lda #1
        sta LBA
        jsr readlow
        ldx #0
copytr:
        lda tramp,x
        sta $0100,x
        inx
        cpx #11
        bne copytr
        jmp $0100

; Drop overlay from RAM at $0100. Clearing $C016 while PC is still in
; $E000–$FFFF makes the next fetch come from SRAM (zeros) instead of ROM.
tramp:
        ldx #$FF
        txs
        lda #0
        sta ROM_CTRL
        jmp $4002

readlow:
        jsr ide_setup
        ldx #0
rl1:
        lda IDE_DATA
        sta (DEST),y
        inc DEST
        inx
        bne rl1
rl2:
        lda IDE_DATA
        inx
        bne rl2
        rts

readsec:
        jsr ide_setup
        lda #2
        sta PAGES
        ldy #0
pgloop:
        ldx #0
byteloop:
        lda IDE_DATA
        jsr putram
        inx
        bne byteloop
        dec PAGES
        bne pgloop
        rts

ide_setup:
waitbsy:
        lda IDE_CMD
        and #$80
        bne waitbsy
        lda LBA
        sta IDE_LBA0
        lda LBA+1
        sta IDE_LBA1
        lda #0
        sta IDE_LBA2
        lda #$E0
        sta IDE_LBA3
        lda #1
        sta IDE_SECCNT
        lda #$20
        sta IDE_CMD
waitdrq:
        lda IDE_CMD
        and #$08
        beq waitdrq
        ldy #0
        rts

putram:
        pha
        lda DEST+1
        cmp #$C0
        beq drop
        cmp #$C1
        beq drop
        cmp #$C2
        beq drop
        pla
        sta (DEST),y
        jmp bump
drop:
        pla
bump:
        inc DEST
        bne bumpd
        inc DEST+1
bumpd:
        rts

skip:
        ldx INPTR
        lda LINE,x
        cmp #' '
        beq skip1
        cmp #9
        beq skip1
        rts
skip1:
        inc INPTR
        jmp skip

parse_addr:
        jsr skip
        lda #0
        sta PTR
        sta PTR+1
        lda #4
        sta COUNT
pa:
        ldx INPTR
        lda LINE,x
        jsr hexval
        bcs pa_done
        inc INPTR
        asl PTR
        rol PTR+1
        asl PTR
        rol PTR+1
        asl PTR
        rol PTR+1
        asl PTR
        rol PTR+1
        ora PTR
        sta PTR
        dec COUNT
        bne pa
pa_done:
        rts

parse_byte:
        jsr skip
        lda #0
        sta COUNT
        jsr nyb
        asl
        asl
        asl
        asl
        sta COUNT
        jsr nyb
        ora COUNT
        rts

nyb:
        ldx INPTR
        lda LINE,x
        jsr hexval
        inc INPTR
        rts

hexval:
        cmp #'0'
        bcc hexbad
        cmp #':'
        bcc hexd
        cmp #'A'
        bcc hexl
        cmp #'G'
        bcc hexu
hexl:
        cmp #'a'
        bcc hexbad
        cmp #'g'
        bcs hexbad
        sec
        sbc #'a'-10
        clc
        rts
hexu:
        sec
        sbc #'A'-10
        clc
        rts
hexd:
        sec
        sbc #'0'
        clc
        rts
hexbad:
        sec
        rts

puthex:
        pha
        lsr
        lsr
        lsr
        lsr
        jsr putnyb
        pla
        and #$0F
        jsr putnyb
        rts

putnyb:
        and #$0F
        cmp #10
        bcc putn
        clc
        adc #'A'-10
        jmp putc
putn:
        clc
        adc #'0'
        jmp putc

nmi:
        jmp (NMIVEC)
irq:
        jmp (IRQVEC)
rom_rti:
        rti

        .org $FFFA
        .word nmi
        .word reset
        .word irq
