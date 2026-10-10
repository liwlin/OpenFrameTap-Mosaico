"""Host regression for video refresh ACK/request correlation helpers."""
import subprocess
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
video = root / "firmware/esp_mosaico/main/oft_video.cpp"
output = root / "artifacts/mosaico/video-refresh-contract"
output.mkdir(parents=True, exist_ok=True)


def extract_function(text: str, name: str) -> str:
    match = re.search(r"static (?:bool|unsigned|void) " + name + r"\(", text)
    assert match is not None
    start = match.start()
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError(f"no complete function body for {name}")


source_text = video.read_text(encoding="utf-8")
helpers = "\n".join(extract_function(source_text, name) for name in (
    "retry_image_only",
    "refresh_success",
    "recover_missing",
    "image_backoff_ms",
    "ack_timeout_delay_ms",
))
start=source_text.index("    if(command>=0){")
brace=source_text.index("{",start);depth=1;end=brace+1
while depth:
    depth+=(source_text[end]=="{")-(source_text[end]=="}");end+=1
command_branch=source_text[start:end]
stop_function=extract_function(source_text,"stop_refresh")
start=source_text.index("else if(now-refresh_wait>OFT_VIDEO_MISSING_TIMEOUT_US")
brace=source_text.index("{",start);depth=1;end=brace+1
while depth:
    depth+=(source_text[end]=="{")-(source_text[end]=="}");end+=1
timeout_branch=source_text[start:end]

source = output / "contract.cpp"
source.write_text(f'''
#include <cstdint>
#include <cstdio>
#include <atomic>
#define CHECK(expr) do {{ if (!(expr)) {{ std::fprintf(stderr, "line %d: %s\\n", __LINE__, #expr); return 1; }} }} while (0)

enum {{ OFT_UDP_OFF, OFT_UDP_HANDSHAKE, OFT_UDP_REGISTER, OFT_UDP_ENABLE, OFT_UDP_READY, OFT_UDP_FAULT, OFT_UDP_ARMING }};
#include "oft_video_policy.h"

struct oft_udp_snapshot_t {{
    int state = OFT_UDP_OFF;
    unsigned keyframe_requests = 0, keyframe_replies = 0, keyframe_failures = 0;
    unsigned keyframe_confirmed_request = 0, keyframe_timeouts = 0, keyframe_timeout_request = 0;
    unsigned keyframe_remote_timeouts = 0;
    int64_t keyframe_sent_us = 0;
    bool keyframe_pending = false;
    bool action_busy = false;
    bool ack_retry_active = false;
}};
struct oft_video_snapshot_t {{
    bool busy = false;
    uint32_t last_idr_generation = 0;
    int64_t last_idr_source_us = 0;
    int64_t lost_idr_source_us = 0;
}};

{helpers}
static bool gui_refresh,allow_begin;
static unsigned refresh_remaining,recovery_level,ack_timeout_retries,refresh_request_count,missed_picture;
static int64_t refresh_wait,refresh_due;
static std::atomic<unsigned> simulated_losses{{0}};
static int mux,cancellations;
static struct {{ bool sparse_live,refresh_recovering;unsigned retry_after_ms,refresh_recoveries,refresh_failures; }} view;
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
static void oft_udp_cancel_keyframe(void) {{ cancellations++; }}
static void detail(const char *) {{}}
{stop_function}
static void process_timeout(const oft_udp_snapshot_t &u,bool shown,int64_t now) {{
    if(false) {{}}
    {timeout_branch}
}}
static bool begin_refresh(unsigned) {{ return allow_begin; }}
static void apply_command(int command) {{
{command_branch}
}}

static oft_udp_snapshot_t ready(unsigned requests) {{
    oft_udp_snapshot_t u;
    u.state = OFT_UDP_READY;
    u.keyframe_requests = requests;
    u.keyframe_sent_us = 1000;
    return u;
}}

int main(void) {{
    oft_video_snapshot_t s;
    s.last_idr_generation = 9;
    s.last_idr_source_us = 1001;

    oft_udp_snapshot_t u = ready(6);
    u.keyframe_replies = 5;                // historical ACK gap remains.
    u.keyframe_confirmed_request = 6;      // current request is matched.
    CHECK(refresh_success(u, s, 5, 8));

    u = ready(6);
    u.keyframe_replies = 6;                // cumulative count caught up.
    u.keyframe_confirmed_request = 5;      // only an old request was confirmed.
    CHECK(!refresh_success(u, s, 5, 8));

    u = ready(6);
    u.keyframe_replies = 5;
    u.keyframe_confirmed_request = 6;
    s.last_idr_generation = 8;             // ACK arrived, picture is missing.
    s.last_idr_source_us = 0;
    CHECK(recover_missing(u, s, 5, 8, true, 0, OFT_VIDEO_MISSING_TIMEOUT_US + 1));

    u = ready(6);
    u.keyframe_timeout_request = 6;
    u.keyframe_timeouts = 1;
    CHECK(retry_image_only(u, 5, true, true));

    u.keyframe_failures = 1; CHECK(!retry_image_only(u, 5, true, true)); u.keyframe_failures = 0;
    u.state = OFT_UDP_FAULT; CHECK(!retry_image_only(u, 5, true, true)); u.state = OFT_UDP_READY;
    u.keyframe_pending = true; CHECK(!retry_image_only(u, 5, true, true)); u.keyframe_pending = false;
    CHECK(!retry_image_only(u, 5, false, true));
    CHECK(!retry_image_only(u, 5, true, false));
    u.action_busy = true; CHECK(!retry_image_only(u, 5, true, true)); u.action_busy = false;
    u.ack_retry_active = true; CHECK(!retry_image_only(u, 5, true, true)); u.ack_retry_active = false;

    CHECK(ack_timeout_delay_ms(0)==4000 && ack_timeout_delay_ms(1)==8000 && ack_timeout_delay_ms(2)==16000);
    CHECK(ack_timeout_delay_ms(3)==0 && ack_timeout_delay_ms(UINT32_MAX)==0);
    gui_refresh=true;allow_begin=false;apply_command(5000);CHECK(gui_refresh);
    allow_begin=true;apply_command(5000);CHECK(!gui_refresh);

    // A local timeout and camera E1 share the real scheduler's one budget.
    gui_refresh=true;ack_timeout_retries=0;view={{}};cancellations=0;
    for(unsigned attempt=0;attempt<4;attempt++){{
        u=ready(attempt+1);u.keyframe_confirmed_request=attempt;
        u.keyframe_timeout_request=attempt+1;u.keyframe_timeouts=attempt+1;
        u.keyframe_remote_timeouts=(attempt+1)/2;
        refresh_request_count=attempt;refresh_wait=1000000;
        // A new image following E1 cannot turn its failed request into success.
        s.last_idr_generation=9;s.last_idr_source_us=1001;
        CHECK(!refresh_success(u,s,attempt,8));
        if(!attempt){{
            u.action_busy=true;process_timeout(u,true,4000000);
            CHECK(ack_timeout_retries==0 && cancellations==0);u.action_busy=false;
        }}
        process_timeout(u,true,4000000);
        if(attempt<3){{
            CHECK(gui_refresh && ack_timeout_retries==attempt+1 && view.refresh_failures==0);
            CHECK(refresh_due==4000000+(int64_t)(4000u<<attempt)*1000 && cancellations==0);
        }}else{{
            CHECK(!gui_refresh && view.refresh_failures==1 && cancellations==1);
            CHECK(!refresh_wait && !refresh_remaining);
        }}
    }}

    std::puts("Video refresh contract passed");
    return 0;
}}
''', encoding="utf-8")

binary = output / "contract"
subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I",str(root / "firmware/esp_mosaico/main"),
                str(source), "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
