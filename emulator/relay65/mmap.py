"""Software-visible memory map — same decode the Memory/System card will use."""

# Logical 6502 space
ZEROPAGE = 0x0000
STACK_PAGE = 0x0100

RAM_FIXED_END = 0x7FFF
WINDOW_BASE = 0x8000
WINDOW_END = 0xBFFF
WINDOW_SIZE = 0x4000

IO_BASE = 0xC000
IO_END = 0xC0FF
# $C100–$C1FF slot 0 CF, $C200–$C2FF slot 1 ESP32; $C300+ is SRAM (FUZIX).
# SLOT2/SLOT3 names are reserved; v0.1 does not decode them as I/O.

UART_DATA = 0xC000
UART_STATUS = 0xC001
UART_CONTROL = 0xC002
UART_RX_READY = 0x01
UART_TX_READY = 0x02

BANK_REG = 0xC010
ROM_CTRL = 0xC016
ROM_ENABLE = 0x01
BOOT_JUMPER = 0xC017  # I/O card DIP: bit0 = autoboot FUZIX from CF

# Four 16 KiB page registers (FUZIX). Cover $0000–$FFFF.
PAGE0 = 0xC018
PAGE1 = 0xC019
PAGE2 = 0xC01A
PAGE3 = 0xC01B

# Semiconductor tick/IRQ (6522-class on the I/O card).
TICK_LO = 0xC020
TICK_HI = 0xC021
TICK_CTRL = 0xC022
TICK_IFR = 0xC023

# RAM-indirect IRQ/NMI pointers. ROM vectors JMP (these).
IRQ_RAMVEC = 0x00F0
NMI_RAMVEC = 0x00F2

SLOT0 = 0xC100
SLOT1 = 0xC200
SLOT2 = 0xC300
SLOT3 = 0xC400
SLOT_SIZE = 0x0100

IDE_BASE = SLOT0
IDE_END = SLOT0 + 7

ESP32_BASE = SLOT1
ESP32_END = SLOT1 + 0x0F

RAM_D000 = 0xD000
RAM_D000_END = 0xDFFF

ROM_BASE = 0xE000
ROM_END = 0xFFFF
ROM_SIZE = 0x2000

NMI_VECTOR = 0xFFFA
RESET_VECTOR = 0xFFFC
IRQ_VECTOR = 0xFFFE

# Physical SRAM: 512 KiB = 32 × 16 KiB pages
PAGE_SHIFT = 14
NUM_PAGES = 32
SRAM_SIZE = NUM_PAGES * WINDOW_SIZE
MAX_PAGE = NUM_PAGES - 1

# Contiki $C010: bank 0 = page 2 ($8000), banks 1–4 = pages 4–7
MAX_BANK = 4
PHYS_FIXED = 0x00000
PHYS_WINDOW0 = 0x08000
PHYS_BANK1 = 0x10000


def window_phys(bank: int, addr: int) -> int:
    """Contiki-style $8000 window (also used to compute page 2)."""
    bank &= 0xFF
    if bank == 0:
        return PHYS_WINDOW0 + (addr & 0x3FFF)
    n = min(max(bank, 1), MAX_BANK)
    return PHYS_BANK1 + (n - 1) * WINDOW_SIZE + (addr & 0x3FFF)


def contiki_bank_to_page(bank: int) -> int:
    return window_phys(bank, WINDOW_BASE) >> PAGE_SHIFT
