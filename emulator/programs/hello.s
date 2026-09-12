; Print a greeting on the UART, then sit in a loop (no magic halt I/O).

        .org $0200

        ldx #0
loop:
        lda msg,x
        beq done
        sta $C000
        inx
        jmp loop
done:
        jmp done

msg:
        .byte "Hello, Relay-65", $0A, 0
