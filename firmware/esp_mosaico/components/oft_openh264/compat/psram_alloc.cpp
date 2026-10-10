#include "esp_heap_caps.h"
#include <stdio.h>
extern "C" void *oft_openh264_malloc(size_t size)
{
    const uint32_t caps=MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT;
    void *p=heap_caps_malloc(size,caps);
    if(!p){
        const size_t available=heap_caps_get_free_size(caps);
        const size_t largest=heap_caps_get_largest_free_block(caps);
        const size_t minimum=heap_caps_get_minimum_free_size(caps);
        printf("OFT_H264_ALLOC_FAIL bytes=%u free=%u largest=%u minimum=%u caps=%lx\n",
            (unsigned)size,(unsigned)available,(unsigned)largest,(unsigned)minimum,(unsigned long)caps);
    }
    return p;
}
