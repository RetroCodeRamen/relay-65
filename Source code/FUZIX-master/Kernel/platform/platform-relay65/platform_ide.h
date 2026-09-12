#define ide_select(x)
#define ide_deselect()

#define IDE_IS_MMIO
#define IDE_8BIT_ONLY

/* CompactFlash in slot 0 */
#define IDE_REG_DATA		0xC100
#define IDE_REG_ERROR		0xC101
#define IDE_REG_FEATURES	0xC101
#define IDE_REG_SEC_COUNT	0xC102
#define IDE_REG_LBA_0		0xC103
#define IDE_REG_LBA_1		0xC104
#define IDE_REG_LBA_2		0xC105
#define IDE_REG_LBA_3		0xC106
#define IDE_REG_DEVHEAD		0xC106
#define IDE_REG_COMMAND		0xC107
#define IDE_REG_STATUS		0xC107
