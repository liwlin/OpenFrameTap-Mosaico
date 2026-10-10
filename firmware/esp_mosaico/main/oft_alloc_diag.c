#include "oft_alloc_diag.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include <stdio.h>

typedef struct {size_t bytes;uint32_t caps;int64_t at_us;char function[32];} failure_t;
static failure_t failures[8];
static unsigned head,count,total,dropped;
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;

/* Heap callbacks may run in task or ISR context. No allocation, heap query,
   formatting or I/O here: main drains a bounded static ring later. */
static void allocation_failed(size_t bytes,uint32_t caps,const char *function)
{
    int64_t at=esp_timer_get_time();
    portENTER_CRITICAL_SAFE(&lock);
    total++;
    if(count<8){
        failure_t *f=&failures[(head+count)%8];
        f->bytes=bytes;f->caps=caps;f->at_us=at;
        unsigned i=0;
        if(function)for(;i<sizeof(f->function)-1&&function[i];i++)f->function[i]=function[i];
        f->function[i]=0;count++;
    }else dropped++;
    portEXIT_CRITICAL_SAFE(&lock);
}
esp_err_t oft_alloc_diag_start(void)
{
    return heap_caps_register_failed_alloc_callback(allocation_failed);
}
void oft_alloc_diag_dump(void)
{
    static unsigned reported;
    /* Limit work even if other tasks keep producing failures during output. */
    for(unsigned i=0;i<8;i++){
        failure_t f;
        portENTER_CRITICAL_SAFE(&lock);
        bool have=count!=0;
        if(have){f=failures[head];head=(head+1)%8;count--;}
        portEXIT_CRITICAL_SAFE(&lock);
        if(!have)break;
        printf("OFT_ALLOC_FAIL event_us=%lld bytes=%u caps=%lx function=%s\n",
            (long long)f.at_us,(unsigned)f.bytes,(unsigned long)f.caps,f.function);
    }
    portENTER_CRITICAL_SAFE(&lock);
    unsigned n=total,lost=dropped,pending=count;
    portEXIT_CRITICAL_SAFE(&lock);
    if(n!=reported){reported=n;printf("OFT_ALLOC_FAIL_TOTAL total=%u dropped=%u pending=%u\n",n,lost,pending);}
}
