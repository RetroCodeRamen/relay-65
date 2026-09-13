; ls: AX = path (0 = cwd). No cc65 multiply, no nexttok.
; Prints ls_blob[id] through uart_puts.

        .export         _vfs_ls
        .import         _uart_puts
        .import         _cwd, _ls_blob
        .importzp        ptr1

        .segment        "CODE"

        .proc   _vfs_ls
        sta     ptr1
        stx     ptr1+1
        ora     ptr1+1
        beq     usecwd
        ldy     #0
skipsp: lda     (ptr1),y
        cmp     #' '
        beq     adv
        cmp     #$09
        bne     first
adv:    iny
        bne     skipsp
first:  cmp     #0
        beq     usecwd
        cmp     #'.'
        beq     dot
        cmp     #'/'
        beq     abs
        ldx     _cwd
        bne     fail
        jsr     letter
        bcs     fail
        bcc     puts
abs:    iny
        lda     (ptr1),y
        beq     root
        jsr     letter
        bcs     fail
        bcc     puts
dot:    iny
        lda     (ptr1),y
        beq     usecwd
        cmp     #'.'
        bne     fail
        iny
        lda     (ptr1),y
        bne     fail
root:   lda     #0
        beq     puts
usecwd: lda     _cwd
puts:   asl     a
        tay
        lda     _ls_blob,y
        ldx     _ls_blob+1,y
        jmp     _uart_puts
fail:   lda     #<err
        ldx     #>err
        jmp     _uart_puts

letter: cmp     #'b'
        beq     i1
        cmp     #'B'
        beq     i1
        cmp     #'e'
        beq     i2
        cmp     #'E'
        beq     i2
        cmp     #'w'
        beq     i3
        cmp     #'W'
        beq     i3
        cmp     #'t'
        beq     i4
        cmp     #'T'
        beq     i4
        sec
        rts
i1:     lda     #1
        clc
        rts
i2:     lda     #2
        clc
        rts
i3:     lda     #3
        clc
        rts
i4:     lda     #4
        clc
        rts
        .endproc

        .segment        "RODATA"
err:    .byte   "ls: not a directory",$0a,$00
