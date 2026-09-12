# Relay-65 FUZIX notes

Banking is four 16K pages at `$C018–$C01B` (not the RCBus `$FE78` quartet).
UART is the 2-register Relay-65 chip, not a 16550.
Timer is `$C023` IFR, not a 6522.
CF is `$C100`, 8-bit PIO.

I/O hole is `$C000–$C2FF`. Kernel may live at `$C300+` (ld65 `RAMC`) and in `$D000–$FDFF`.
