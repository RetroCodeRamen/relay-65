; UART $C000 data, $C001 status (bit0 RX, bit1 TX).
; This CPU cannot outrun a silicon UART, so TX-ready is not polled.

        .export         _write
        .export         _uart_putc
        .export         _uart_puts
        .export         _uart_putn
        .export         _uart_read_line
        .export         _uart_getc
        .export         _uart_delay10
        .export         _vfs_ls_need
        .export         _uart_idle
        .import         popax, popptr1
        .importzp        ptr1, ptr2, ptr3

UART_DATA   = $C000
UART_STATUS = $C001

        .data
_vfs_ls_need:
        .byte   0
_uart_idle:
        .word   0

        .code
        .proc   _uart_putc
        sta     UART_DATA
        rts
        .endproc

        .proc   _uart_puts
        sta     ptr1
        stx     ptr1+1
        ldy     #0
loop:   lda     (ptr1),y
        beq     done
        sta     UART_DATA
        iny
        bne     loop
        inc     ptr1+1
        jmp     loop
done:   rts
        .endproc

        .proc   _uart_putn
        sta     ptr2
        stx     ptr2+1
        jsr     popptr1
        lda     ptr2
        ora     ptr2+1
        beq     done
        ldy     #0
loop:   lda     (ptr1),y
        sta     UART_DATA
        iny
        bne     decn
        inc     ptr1+1
decn:   lda     ptr2
        bne     lo
        dec     ptr2+1
lo:     dec     ptr2
        lda     ptr2
        ora     ptr2+1
        bne     loop
done:   rts
        .endproc

; unsigned char __fastcall__ uart_getc(void);
; Wait for RX. No echo.
        .proc   _uart_getc
wait:   lda     UART_STATUS
        lsr     a
        bcc     wait
        lda     UART_DATA
        ldx     #0
        rts
        .endproc

; void uart_delay10(void);
; About ten 6502 NOPs (one extra RTS).
        .proc   _uart_delay10
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        nop
        rts
        .endproc

; void __fastcall__ uart_read_line(char *buf);
; Tight poll — no C idle while waiting for keys.
; BS ($08) and DEL ($7F) rub out the last character (BS, space, BS on TX).
        .proc   _uart_read_line
        sta     ptr1
        stx     ptr1+1
        ldy     #0
wait:   lda     UART_STATUS
        lsr     a
        bcc     wait
        lda     UART_DATA
        cmp     #$08
        beq     rub
        cmp     #$7f
        beq     rub
        cmp     #$0d
        beq     crlf
        cmp     #$0a
        beq     lf
        sta     UART_DATA
        sta     (ptr1),y
        iny
        cpy     #62
        bcc     wait
        bcs     endl
rub:    cpy     #0
        beq     wait
        dey
        lda     #$08
        sta     UART_DATA
        lda     #$20
        sta     UART_DATA
        lda     #$08
        sta     UART_DATA
        jmp     wait
lf:     sta     UART_DATA
        jmp     endl
crlf:   lda     #$0d
        sta     UART_DATA
        lda     #$0a
        sta     UART_DATA
endl:   lda     #0
        sta     (ptr1),y
        rts
        .endproc

        .proc   _write
        sta     ptr3
        stx     ptr3+1
        inx
        stx     ptr2+1
        tax
        inx
        stx     ptr2
        jsr     popptr1
        jsr     popax

begin:  dec     ptr2
        bne     outch
        dec     ptr2+1
        beq     done

outch:  ldy     #0
        lda     (ptr1),y
        sta     UART_DATA
        inc     ptr1
        bne     begin
        inc     ptr1+1
        jmp     begin

done:   lda     ptr3
        ldx     ptr3+1
        rts
        .endproc
