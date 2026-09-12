; int __fastcall__ write(int fd, const void* buf, unsigned count);
; Last arg (count) in AX. Polls UART_STATUS bit 1, writes UART_DATA.

        .export         _write
        .import         popax, popptr1
        .importzp        ptr1, ptr2, ptr3

UART_DATA   = $C000
UART_STATUS = $C001

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

outch:  lda     UART_STATUS
        and     #$02
        beq     outch
        ldy     #0
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
