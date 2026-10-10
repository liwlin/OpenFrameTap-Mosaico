"""Host contract for UDP session behavior while joystick guard-fault paused."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
udp = root / "firmware/esp_mosaico/main/oft_udp.c"
component = root / "firmware/esp_mosaico/components/oft_protocol"
output = root / "artifacts/mosaico/control-session-guard-contract"
output.mkdir(parents=True, exist_ok=True)


def extract_block(text: str, needle: str) -> str:
    start = text.index(needle)
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError(needle)


def extract_segment(text: str, start_needle: str, end_needle: str) -> str:
    start = text.index(start_needle)
    end = text.index(end_needle, start) + len(end_needle)
    return text[start:end]


text = udp.read_text(encoding="utf-8")
fault_block = extract_block(text, "if(OFT_P3_TOUCH_CONTROL_VALIDATED&&c->state==OFT_CONTROL_FAULT)")
receipt_helper = extract_block(text, "static bool guard_stop_receipt_ready(void)")
mode_block = extract_block(text, "if(mode>=0)")
rearm_segment = extract_segment(
    text,
    "if(oft_control_rearm_on_release",
    "portENTER_CRITICAL(&mux);view.control_state=c->state;portEXIT_CRITICAL(&mux);",
)
source = output / "contract.c"
source.write_text(f'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdatomic.h>
#include "oft_control.h"
#define CHECK(expr) do {{ if (!(expr)) {{ fprintf(stderr, "line %d: %s\\n", __LINE__, #expr); return 1; }} }} while (0)
#define OFT_P3_TOUCH_CONTROL_VALIDATED 1
#define OFT_UDP_READY 4
#define OFT_UDP_FAULT 5
#define TAG "test"
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
typedef int portMUX_TYPE;
static portMUX_TYPE mux;
typedef struct {{ bool active; }} oft_head_result_t;
typedef struct {{
    int state;
    bool zero_receipt_confirmed, head_held, head_tracking, head_release_required, head_mode;
    int64_t zero_receipt_us;
    int control_state;
    unsigned head_limit_mask;
    int64_t last_packet_us;
    char detail[96];
}} view_t;
static view_t view;
static oft_input_t latest_input, input, release;
static oft_control_t control;
static int64_t guard_stop_deadline, input_now, fake_now = 1000000;
static int state_before, mode;
static bool link_fresh, action_pending, head_reference_valid, head_hold_blocked, haptic_off;
static int close_count, close_fault, cancel_count, init_count, head_target;
static int control_calls, control_y, control_p;
static unsigned head_generation;
static atomic_bool head_new_press;
static oft_head_result_t head_result;
{receipt_helper}
static size_t strlcpy(char *dst, const char *src, size_t cap) {{
    size_t n = strlen(src);
    if (cap) {{ size_t c = n >= cap ? cap - 1 : n; memcpy(dst, src, c); dst[c] = 0; }}
    return n;
}}
static int64_t esp_timer_get_time(void) {{ return fake_now; }}
static void oft_motion_haptic(bool on) {{ if (!on) haptic_off = true; }}
static void oft_head_target_cancel(void *unused) {{ (void)unused; cancel_count++; }}
static bool control_send(int y, int p, void *ctx) {{ (void)ctx; control_calls++; control_y = y; control_p = p; return true; }}
static bool mock_send(int y, int p, void *ctx) {{ return control_send(y, p, ctx); }}
static void close_session(bool fault, const char *detail) {{
    close_count++;
    close_fault = fault;
    view.state = fault ? OFT_UDP_FAULT : 0;
    strlcpy(view.detail, detail, sizeof(view.detail));
}}
static bool send_capture(int y, int p, void *ctx) {{
    (void)y; (void)p; (void)ctx; return true;
}}
static oft_input_t make_input(uint32_t gesture, bool active, int64_t at) {{
    oft_input_t in = {{.yaw = 1.0f, .pitch = 0.0f, .timestamp_us = at, .gesture = gesture, .active = active}};
    return in;
}}
static void reset_world(void) {{
    memset(&view, 0, sizeof(view)); memset(&control, 0, sizeof(control));
    memset(&latest_input, 0, sizeof(latest_input)); memset(&head_result, 0, sizeof(head_result));
    guard_stop_deadline = input_now = 0; state_before = mode = close_count = close_fault = cancel_count = init_count = 0;
    control_calls = control_y = control_p = 0;
    head_generation=0;atomic_store(&head_new_press,false);
    link_fresh = action_pending = head_reference_valid = head_hold_blocked = haptic_off = false;
    view.state = OFT_UDP_READY; view.zero_receipt_confirmed = false; fake_now = 1000000;
}}
static void init_control(oft_control_t *c) {{ init_count++; oft_control_init(c); }}
#define oft_control_init init_control
static int make_guard_fault(void) {{
    oft_control_init(&control);
    input = make_input(7, true, 1000000);
    oft_control_tick(&control, &input, true, 1000000, send_capture, NULL);
    CHECK(control.state == OFT_CONTROL_ACTIVE);
    oft_control_tick(&control, &input, false, 1030000, send_capture, NULL);
    CHECK(oft_control_is_guard_fault(&control));
    return 0;
}}
static void run_fault_block(oft_control_t *c) {{
{fault_block}
}}
static void run_mode_block(void) {{
{mode_block}
}}
static void run_rearm_segment(oft_control_t *c) {{
{rearm_segment}
}}
int main(void) {{
    reset_world(); CHECK(make_guard_fault() == 0);
    state_before = OFT_CONTROL_ACTIVE; input_now = 1100000; link_fresh = false;
    run_fault_block(&control);
    CHECK(close_count == 0);
    CHECK(view.state == OFT_UDP_READY);
    CHECK(guard_stop_deadline == 1400000);
    CHECK(view.head_release_required && !view.head_held && !view.head_tracking);
    CHECK(haptic_off && cancel_count == 1);

    state_before = OFT_CONTROL_FAULT; input_now = 1399999; run_fault_block(&control);
    CHECK(close_count == 0 && guard_stop_deadline == 1400000);
    input_now = 1400000; run_fault_block(&control);
    CHECK(close_count == 1 && close_fault && view.state == OFT_UDP_FAULT);

    reset_world(); CHECK(make_guard_fault() == 0);
    state_before = OFT_CONTROL_ACTIVE; input_now = 2000000; run_fault_block(&control);
    CHECK(guard_stop_deadline == 2300000 && close_count == 0);
    view.zero_receipt_confirmed = true; view.zero_receipt_us=2050000; state_before = OFT_CONTROL_FAULT; input_now = 2050000; run_fault_block(&control);
    CHECK(guard_stop_deadline == 0 && close_count == 0 && view.state == OFT_UDP_READY);

    reset_world(); CHECK(make_guard_fault() == 0);
    state_before = OFT_CONTROL_ACTIVE; input_now = 5000000; run_fault_block(&control);
    CHECK(guard_stop_deadline == 5300000 && close_count == 0);
    view.zero_receipt_confirmed = true; view.zero_receipt_us = 5300001;
    state_before = OFT_CONTROL_FAULT; input_now = 5300001; run_fault_block(&control);
    CHECK(close_count == 1 && close_fault && view.state == OFT_UDP_FAULT);

    reset_world(); CHECK(make_guard_fault() == 0);
    state_before = OFT_CONTROL_ACTIVE; input_now = 6000000; run_fault_block(&control);
    CHECK(guard_stop_deadline == 6300000 && close_count == 0);
    view.zero_receipt_confirmed = true; view.zero_receipt_us = 6299999;
    state_before = OFT_CONTROL_FAULT; input_now = 6300001; run_fault_block(&control);
    CHECK(guard_stop_deadline == 0 && close_count == 0 && view.state == OFT_UDP_READY);

    reset_world(); control.state = OFT_CONTROL_FAULT; control.failures = 1;
    state_before = OFT_CONTROL_ACTIVE; input_now = 3000000; run_fault_block(&control);
    CHECK(close_count == 1 && close_fault && view.state == OFT_UDP_FAULT);

    reset_world(); CHECK(make_guard_fault() == 0);
    guard_stop_deadline = 3333333; mode = 1; fake_now = 4000000; init_count = 0;
    run_mode_block();
    CHECK(close_count == 0);
    CHECK(init_count == 0);
    CHECK(control.state == OFT_CONTROL_FAULT);
    CHECK(guard_stop_deadline == 3333333);
    CHECK(view.head_mode && !view.head_held);

    reset_world(); CHECK(make_guard_fault() == 0);
    view.zero_receipt_confirmed = true; view.zero_receipt_us = 7000000; view.last_packet_us = 7000000;
    input_now = 7000000; link_fresh = true; action_pending = false;
    release = make_input(7, false, 7000000);
    input = make_input(8, true, 7000000);
    run_rearm_segment(&control);
    CHECK(control_calls == 0);
    CHECK(control.state != OFT_CONTROL_ACTIVE);
    input = make_input(7, true, 7100000);
    oft_control_tick(&control, &input, true, 7100000, control_send, NULL);
    CHECK(control_calls == 0);
    input = make_input(8, true, 7200000);
    oft_control_tick(&control, &input, true, 7200000, control_send, NULL);
    CHECK(control_calls == 1 && control_y != 0 && control.state == OFT_CONTROL_ACTIVE);
    reset_world(); CHECK(make_guard_fault() == 0);
    view.head_mode=true;head_generation=8;atomic_store(&head_new_press,true);
    view.zero_receipt_confirmed=true;view.zero_receipt_us=8000000;view.last_packet_us=8000000;
    input_now=8000000;link_fresh=true;action_pending=false;
    release=make_input(0x80000008u,false,input_now);
    input=make_input(0x80000008u,true,input_now);
    run_rearm_segment(&control);
    CHECK(control_calls==0 && control.state!=OFT_CONTROL_ACTIVE && head_hold_blocked);
    CHECK(control.blocked_gesture==0x80000008u && !atomic_load(&head_new_press));
    input=make_input(0x80000008u,true,8100000);
    oft_control_tick(&control,&input,true,8100000,control_send,NULL);CHECK(control_calls==0);
    input=make_input(0x80000009u,true,8200000);
    oft_control_tick(&control,&input,true,8200000,control_send,NULL);CHECK(control_calls==1);
    puts("Control session guard contract passed");
    return 0;
}}
''', encoding="utf-8")
binary = output / "contract"
subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-variable",
                "-ffunction-sections", "-fdata-sections", "-I", str(component / "include"),
                str(source), str(component / "oft_control.c"), "-Wl,--gc-sections",
                "-lm", "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
