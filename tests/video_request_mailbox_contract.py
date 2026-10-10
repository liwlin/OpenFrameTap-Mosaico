"""Exercise the real UDP keyframe mailbox under transient send gates."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
text = (root / "firmware/esp_mosaico/main/oft_udp.c").read_text(encoding="utf-8")
start = text.index("    /* Consume the one-slot request")
brace = text.index("{", start)
depth, end = 1, brace + 1
while depth:
    depth += (text[end] == "{") - (text[end] == "}")
    end += 1
send_block = text[start:end]
assert "atomic_exchange(&keyframe_requested,false)" in send_block

output = root / "artifacts/mosaico/video-request-mailbox-contract"
output.mkdir(parents=True, exist_ok=True)
source = output / "contract.c"
source.write_text(r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdatomic.h>
#include "oft_video_policy.h"
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); return 1; } } while (0)
#define OFT_UDP_READY 4
#define OFT_P3_ENABLE 1
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
static int mux;
static atomic_bool keyframe_requested;
static bool action_pending, keyframe_pending, send_ok;
static uint16_t keyframe_sequence;
static int64_t keyframe_deadline;
static unsigned sends;
static struct { bool retrying; } ack_tx;
static struct {
    int state;
    unsigned keyframe_failures, keyframe_requests;
    bool keyframe_pending;
    int64_t started_us, keyframe_sent_us;
} view;
static bool profile(int command, int a, int b, uint16_t *sequence) {
    (void)command; (void)a; (void)b;
    sends++; *sequence = 42; return send_ok;
}
static void tick(int64_t now) {
''' + send_block + r'''
}
static void reset(void) {
    view.state=OFT_UDP_READY; view.keyframe_failures=0;
    view.keyframe_requests=0; view.keyframe_pending=false;
    view.started_us=1000000; view.keyframe_sent_us=0;
    action_pending=keyframe_pending=ack_tx.retrying=false;
    send_ok=true; sends=0; keyframe_deadline=0;
    atomic_store(&keyframe_requested,true);
}
int main(void) {
    // A request was accepted, but an action started before the writer ran.
    reset(); action_pending=true;
    tick(10000000);
    CHECK(sends==0 && atomic_load(&keyframe_requested));
    action_pending=false; tick(10000001);
    CHECK(sends==1 && !atomic_load(&keyframe_requested));
    CHECK(view.keyframe_requests==1 && view.keyframe_pending && keyframe_pending);
    CHECK(view.keyframe_sent_us==10000001 && keyframe_deadline==13000001);
    keyframe_pending=false; tick(20000000); CHECK(sends==1);

    // Each other temporary gate retains the one-slot request without sending.
    reset(); ack_tx.retrying=true; tick(10000000);
    CHECK(sends==0 && atomic_load(&keyframe_requested));
    ack_tx.retrying=false; tick(10000001); CHECK(sends==1);
    reset(); keyframe_pending=true; tick(10000000);
    CHECK(sends==0 && atomic_load(&keyframe_requested));
    keyframe_pending=false; tick(10000001); CHECK(sends==1);
    reset(); tick(5999999);
    CHECK(sends==0 && atomic_load(&keyframe_requested));
    tick(6000000); CHECK(sends==1);
    reset(); view.keyframe_sent_us=9000000;
    tick(9000000+(int64_t)OFT_VIDEO_MIN_INTERVAL_MS*1000-1);
    CHECK(sends==0 && atomic_load(&keyframe_requested));
    tick(9000000+(int64_t)OFT_VIDEO_MIN_INTERVAL_MS*1000); CHECK(sends==1);

    // A request from an ineligible/failed session is discarded, not deferred.
    reset(); view.state=3; tick(10000000);
    CHECK(sends==0 && !atomic_load(&keyframe_requested));
    view.state=OFT_UDP_READY; tick(10000001); CHECK(sends==0);
    reset(); view.keyframe_failures=1; tick(10000000);
    CHECK(sends==0 && !atomic_load(&keyframe_requested));
    view.keyframe_failures=0; tick(10000001); CHECK(sends==0);

    // An actual send failure remains terminal; do not turn it into a retry.
    reset(); send_ok=false; tick(10000000);
    CHECK(sends==1 && view.keyframe_requests==1 && view.keyframe_failures==1);
    CHECK(!keyframe_pending && !view.keyframe_pending && !atomic_load(&keyframe_requested));
    tick(20000000); CHECK(sends==1);
    puts("Video request mailbox contract passed");
    return 0;
}
''', encoding="utf-8")
binary = output / "contract"
subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(root / "firmware/esp_mosaico/main"),
                str(source), "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
