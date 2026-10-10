"""Host regression for joystick guard-fault rearm rules."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
component = root / "firmware/esp_mosaico/components/oft_protocol"
output = root / "artifacts/mosaico/control-guard-contract"
output.mkdir(parents=True, exist_ok=True)
source = output / "contract.c"
source.write_text(r'''
#include <stdio.h>
#include "oft_control.h"
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); return 1; } } while (0)
typedef struct { unsigned calls; int y[16], p[16]; bool fail; } writer_t;
static bool send_capture(int y, int p, void *opaque) {
    writer_t *w = (writer_t *)opaque;
    if (w->calls < 16) { w->y[w->calls] = y; w->p[w->calls] = p; }
    w->calls++;
    return !w->fail;
}
static oft_input_t input(uint32_t gesture, bool active, int64_t at) {
    oft_input_t in = {.yaw = 1.0f, .pitch = 0.0f, .timestamp_us = at, .gesture = gesture, .active = active};
    return in;
}
static int make_guard_fault(oft_control_t *c, writer_t *w) {
    oft_control_init(c);
    *w = (writer_t){0};
    oft_input_t held = input(7, true, 1000000);
    oft_control_tick(c, &held, true, 1000000, send_capture, w);
    CHECK(c->state == OFT_CONTROL_ACTIVE);
    oft_control_tick(c, &held, false, 1030000, send_capture, w);
    CHECK(w->calls == 2);
    CHECK(w->y[1] == 0 && w->p[1] == 0);
    CHECK(oft_control_is_guard_fault(c));
    return 0;
}
int main(void) {
    oft_control_t c;
    writer_t w;
    CHECK(make_guard_fault(&c, &w) == 0);
    oft_input_t held = input(7, true, 1030000);
    CHECK(!oft_control_rearm_on_release(&c, &held, true, 1030000));
    CHECK(oft_control_is_guard_fault(&c));
    oft_input_t stale_release = input(7, false, 700000);
    CHECK(!oft_control_rearm_on_release(&c, &stale_release, true, 1030000));
    oft_input_t future_release = input(7, false, 1030001);
    CHECK(!oft_control_rearm_on_release(&c, &future_release, true, 1030000));
    oft_input_t release = input(7, false, 1030000);
    CHECK(!oft_control_rearm_on_release(&c, &release, false, 1030000));
    CHECK(oft_control_rearm_on_release(&c, &release, true, 1030000));
    CHECK(c.state == OFT_CONTROL_DISABLED);
    CHECK(c.have_blocked_gesture && c.blocked_gesture == 7);
    oft_control_tick(&c, &held, true, 1030000, send_capture, &w);
    CHECK(w.calls == 2);                  // held old gesture cannot resume.
    oft_input_t next = input(8, true, 1130000);
    oft_control_tick(&c, &next, true, 1130000, send_capture, &w);
    CHECK(w.calls == 3 && c.state == OFT_CONTROL_ACTIVE);

    CHECK(make_guard_fault(&c, &w) == 0);
    CHECK(!oft_control_rearm_on_release(NULL, &release, true, 1030000));
    CHECK(!oft_control_rearm_on_release(&c, NULL, true, 1030000));

    oft_control_init(&c); w = (writer_t){0};
    oft_input_t active = input(1, true, 2000000);
    oft_control_tick(&c, &active, true, 2000000, send_capture, &w);
    w.fail = true;
    oft_control_stop(&c, true, 2000001, send_capture, &w);
    CHECK(c.state == OFT_CONTROL_FAULT && c.failures > 0);
    CHECK(!oft_control_is_guard_fault(&c));
    oft_input_t failed_release = input(1, false, 2000001);
    CHECK(!oft_control_rearm_on_release(&c, &failed_release, true, 2000001));

    oft_control_init(&c); w = (writer_t){.fail = true};
    oft_input_t failed_start = input(2, true, 3000000);
    oft_control_tick(&c, &failed_start, true, 3000000, send_capture, &w);
    CHECK(c.state == OFT_CONTROL_FAULT && c.failures > 0);
    CHECK(!oft_control_rearm_on_release(&c, &failed_release, true, 3000000));
    puts("Control guard contract passed");
    return 0;
}
''', encoding="utf-8")
binary = output / "contract"
subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-ffunction-sections", "-fdata-sections", "-I", str(component / "include"),
                str(source), str(component / "oft_control.c"), "-Wl,--gc-sections",
                "-lm", "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
