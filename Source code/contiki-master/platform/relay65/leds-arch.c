#include "dev/leds.h"

void leds_arch_init(void) {}
unsigned char leds_arch_get(void) { return 0; }
void leds_arch_set(unsigned char leds) { (void)leds; }
