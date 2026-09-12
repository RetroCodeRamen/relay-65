#include <kernel.h>
#include <kdata.h>
#include <printf.h>
#include "esp32nic.h"

#define ESP32_ID	((volatile uint8_t *)0xC200)
#define ESP32_MAGIC	((volatile uint8_t *)0xC201)
#define ESP32_STATUS	((volatile uint8_t *)0xC202)
#define ESP32_CMD	((volatile uint8_t *)0xC203)
#define ESP32_DATA	((volatile uint8_t *)0xC204)
#define ESP32_LENL	((volatile uint8_t *)0xC205)
#define ESP32_LENH	((volatile uint8_t *)0xC206)

#define ESP32_ST_RX	0x01
#define ESP32_ST_LINK	0x04
#define ESP32_CMD_TX	0x01
#define ESP32_CMD_RX	0x02

uint8_t esp32_present;

void esp32_init(void)
{
	if (*ESP32_ID != 'E' || *ESP32_MAGIC != '2') {
		kputs("ESP32: not found\n");
		esp32_present = 0;
		return;
	}
	esp32_present = 1;
	if (*ESP32_STATUS & ESP32_ST_LINK)
		kputs("ESP32: link up (TCP lives on the card)\n");
	else
		kputs("ESP32: present, no link\n");
}

void esp32_poll(void)
{
}
