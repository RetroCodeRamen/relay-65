#ifndef RTIMER_ARCH_H_
#define RTIMER_ARCH_H_

#include "contiki-conf.h"

#define RTIMER_ARCH_SECOND CLOCK_CONF_SECOND
#define rtimer_arch_now() clock_time()

#endif /* RTIMER_ARCH_H_ */
