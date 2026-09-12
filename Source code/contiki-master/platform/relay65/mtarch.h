#ifndef MTARCH_H_
#define MTARCH_H_

#define MTARCH_CPUSTACKSIZE 64
#define MTARCH_CSTACKSIZE   64
#define MTARCH_ZPSIZE       26

struct mtarch_thread {
  unsigned char dummy;
};

void mtarch_init(void);
void mtarch_remove(void);
void mtarch_start(struct mtarch_thread *thread, void (*function)(void *), void *data);
void mtarch_yield(void);
void mtarch_exec(struct mtarch_thread *thread);
void mtarch_stop(struct mtarch_thread *thread);
void mtarch_pstart(void);
void mtarch_pstop(void);

#endif /* MTARCH_H_ */
