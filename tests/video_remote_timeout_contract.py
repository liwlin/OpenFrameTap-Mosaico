"""Replay a sanitized 09/A8 E1 reply through the real decoder and reply branch."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
text=(root/'firmware/esp_mosaico/main/oft_udp.c').read_text(encoding='utf-8')

def block(needle):
    start=text.index(needle);brace=text.index('{',start);end=brace+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

handler=block('if(keyframe_pending&&reply(f,0x41,9,0xa8,keyframe_sequence))')
startup=block('if(view.state==OFT_UDP_ENABLE&&reply(f,0x41,9,0xa8,enable_sequence))')
reply=block('static bool reply(')
out=root/'artifacts/mosaico/video-remote-timeout-contract';out.mkdir(parents=True,exist_ok=True)
source=out/'contract.c'
source.write_text(r'''
#include <stdio.h>
#include <string.h>
#include "oft_duml.h"
#define CHECK(x) do { if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;} } while(0)
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
#define ESP_LOGW(...) ((void)0)
#define TAG "test"
static int mux;
static bool keyframe_pending;
static uint16_t keyframe_sequence;
enum { OFT_UDP_ENABLE=3,OFT_UDP_READY=4,OFT_UDP_FAULT=5 };
static uint16_t enable_sequence;
static bool enabled;
static int close_count;
static int64_t deadline,next_heartbeat;
static struct {
    int state;
    bool keyframe_pending;
    unsigned keyframe_requests,keyframe_replies,keyframe_failures,keyframe_confirmed_request;
    unsigned keyframe_timeouts,keyframe_timeout_request,keyframe_remote_timeouts;
} view;
static int64_t esp_timer_get_time(void){return 2000000;}
static void close_session(bool fault,const char *message){(void)message;close_count++;view.state=fault?OFT_UDP_FAULT:0;}
static void state(int value,const char *message){(void)message;view.state=value;}
static void log_duml(const char *tag,const uint8_t *raw,size_t size){(void)tag;(void)raw;(void)size;}
''' + reply + r'''
static void handle(const oft_duml_frame_t *f){
''' + handler + startup + r'''
}
static bool dispatch(const uint8_t *raw,size_t size){
    oft_duml_frame_t decoded;if(!oft_duml_decode(raw,size,&decoded))return false;
    handle(&decoded);
    return true;
}
static void reset(void){
    memset(&view,0,sizeof(view));view.keyframe_requests=91;
    view.keyframe_replies=view.keyframe_confirmed_request=90;
    keyframe_pending=view.keyframe_pending=true;keyframe_sequence=1199;
    view.state=OFT_UDP_READY;enable_sequence=1199;enabled=false;close_count=0;deadline=next_heartbeat=0;
}
int main(void){
    // Camera -> app, 2026-10-10 capture request91; header contains no identifiers/media/credentials.
    const uint8_t captured[]={0x55,0x0e,0x04,0x66,0x41,0x02,0xaf,0x04,0xc0,0x09,0xa8,0xe1,0x55,0x22};
    reset();CHECK(dispatch(captured,sizeof(captured)));
    CHECK(!keyframe_pending && !view.keyframe_pending);
    CHECK(view.keyframe_failures==0 && view.keyframe_timeouts==1 && view.keyframe_remote_timeouts==1);
    CHECK(view.keyframe_timeout_request==91 && view.keyframe_confirmed_request==90 && view.keyframe_replies==90);
    CHECK(dispatch(captured,sizeof(captured)));CHECK(view.keyframe_remote_timeouts==1);
    uint8_t raw[32],payload[2];size_t size;
    for(unsigned flags=0x80;flags<=0xc0;flags+=0x40){
        for(unsigned code=0;code<256;code++){
            reset();payload[0]=(uint8_t)code;
            size=oft_duml_encode(raw,sizeof(raw),0x41,2,1199,(uint8_t)flags,9,0xa8,payload,1);
            CHECK(size && dispatch(raw,size));
            if(code==0){CHECK(view.keyframe_replies==91 && view.keyframe_confirmed_request==91 && !view.keyframe_timeouts && !view.keyframe_failures);}
            else if(code==0xe1){CHECK(view.keyframe_timeouts==1 && view.keyframe_remote_timeouts==1 && !view.keyframe_failures && view.keyframe_confirmed_request==90);}
            else{CHECK(view.keyframe_failures==1 && !view.keyframe_timeouts && view.keyframe_confirmed_request==90);}
        }
    }
    payload[0]=0xe1;payload[1]=0;
    for(unsigned n=0;n<=2;n+=2){
        reset();size=oft_duml_encode(raw,sizeof(raw),0x41,2,1199,0xc0,9,0xa8,payload,n);
        CHECK(dispatch(raw,size));CHECK(view.keyframe_failures==1 && !view.keyframe_timeouts);
    }
    // Valid CRC but wrong identity/sequence/command/flags must not consume the request.
    for(unsigned mutation=0;mutation<6;mutation++){
        reset();size=oft_duml_encode(raw,sizeof(raw),mutation==0?0x40:0x41,mutation==1?3:2,
            mutation==2?1198:1199,mutation==3?0x40:0xc0,mutation==4?8:9,mutation==5?0xa9:0xa8,payload,1);
        CHECK(dispatch(raw,size));CHECK(keyframe_pending && view.keyframe_pending && !view.keyframe_timeouts && !view.keyframe_failures);
    }
    reset();memcpy(raw,captured,sizeof(captured));raw[13]^=1;
    CHECK(!dispatch(raw,sizeof(captured)));CHECK(keyframe_pending && !view.keyframe_timeouts);
    // Startup enable is deliberately excluded from preview recovery.
    reset();keyframe_pending=view.keyframe_pending=false;view.state=OFT_UDP_ENABLE;
    CHECK(dispatch(captured,sizeof(captured)));
    CHECK(close_count==1 && view.state==OFT_UDP_FAULT && !enabled && !view.keyframe_timeouts);
    puts("Video remote timeout contract passed (only one-byte E1 is retryable; never success)");
    return 0;
}
''',encoding='utf-8')
component=root/'firmware/esp_mosaico/components/oft_protocol'
binary=out/'contract'
subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-I',str(component/'include'),str(source),str(component/'oft_duml.c'),'-o',str(binary)],check=True)
subprocess.run([str(binary)],check=True)
