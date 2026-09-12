#ifndef CONTIKI_CONF_H_
#define CONTIKI_CONF_H_

#include <stdint.h>
#include <stddef.h>

/* cc65 6502 calling conventions */
#define CC_CONF_REGISTER_ARGS          1
#define CC_CONF_FUNCTION_POINTER_ARGS 1
#define CC_CONF_VA_ARGS                1
#define CC_CONF_INLINE

#define CCIF
#define CLIF

typedef uint8_t   u8_t;
typedef uint16_t u16_t;
typedef uint32_t u32_t;
typedef int32_t  s32_t;

typedef unsigned short clock_time_t;
typedef unsigned short uip_stats_t;

/* $C020 is Φ2 through an 8-bit prescaler. CLOCK_SECOND is that tick rate. */
#define CLOCK_CONF_SECOND 2048
#define AUTOSTART_ENABLE 1

#define RTIMER_ARCH_SECOND CLOCK_CONF_SECOND
#define RTIMER_CONF_GUARD_TIME 2

/* Hello-world / console first. Networking is a later card. */
#define NETSTACK_CONF_WITH_IPV6 0
#define UIP_CONF_IPV6_RPL       0
#define NETSTACK_CONF_WITH_IPV4 0
#define NETSTACK_CONF_WITH_RIME 0

#define UIP_CONF_BUFFER_SIZE 128
#define UIP_CONF_MAX_CONNECTIONS 1
#define UIP_CONF_MAX_LISTENPORTS 1
#define UIP_CONF_UDP 0
#define UIP_CONF_TCP 0
#define UIP_CONF_LOGGING 0

#define LOG_CONF_ENABLED 0

#define PROCESS_CONF_NO_PROCESS_NAMES 1
#define PROCESS_CONF_NUMEVENTS 8
#define PROCESS_CONF_STATS 0

#define SERIAL_LINE_CONF_BUFSIZE 64

#endif /* CONTIKI_CONF_H_ */
