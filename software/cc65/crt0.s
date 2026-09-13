; Relay-65 cc65 startup. Programs are RAM-loaded, so BSS zeros are in the
; image (cfg BSS type=rw). No zerobss loop, no constructor table.

        .export         _exit
        .export         __STARTUP__ : absolute = 1
        .import         _main
        .import         __STACKSTART__
        .import         __MAIN_LAST__
        .export         _basic_heaptop

_basic_heaptop = __MAIN_LAST__

        .include        "zeropage.inc"

IRQVEC = $00F0
NMIVEC = $00F2

        .segment "STARTUP"

        ldx     #$FF
        txs
        lda     #<__STACKSTART__
        ldx     #>__STACKSTART__
        sta     c_sp
        stx     c_sp+1

        lda     #<irq_handler
        sta     IRQVEC
        lda     #>irq_handler
        sta     IRQVEC+1
        lda     #<rti_stub
        sta     NMIVEC
        lda     #>rti_stub
        sta     NMIVEC+1

        jsr     _main
_exit:  jmp     _exit

irq_handler:
        pha
        lda     #$80
        sta     $C023
        pla
        rti

rti_stub:
        rti
