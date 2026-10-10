"""Exercise the production Pocket 3 control heartbeat payload filter."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
component = root / "firmware/esp_mosaico/components/oft_protocol"
output = root / "artifacts/mosaico/heartbeat-contract"
output.mkdir(parents=True, exist_ok=True)
source = output / "contract.c"
source.write_text(r'''
#include <stdint.h>
#include <stdio.h>
#include "oft_pocket3.h"
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); return 1; } } while (0)
static void fill(uint8_t *p, uint8_t tilt, uint8_t speed) {
    p[0] = 0; p[1] = 1; p[2] = 4; p[3] = 1;
    p[4] = tilt; p[5] = 5; p[6] = 1; p[7] = speed;
}
int main(void) {
    uint8_t p[16] = {0};
    for (uint8_t tilt = 0; tilt <= 1; ++tilt) {
        for (uint8_t speed = 0; speed <= 2; ++speed) {
            fill(p, tilt, speed);
            CHECK(oft_p3_control_heartbeat_payload_valid(p, 8));
        }
    }
    CHECK(!oft_p3_control_heartbeat_payload_valid(NULL, 8));
    fill(p, 0, 1);
    for (size_t n = 0; n < 8; ++n) CHECK(!oft_p3_control_heartbeat_payload_valid(p, n));
    for (size_t n = 9; n <= sizeof(p); ++n) CHECK(!oft_p3_control_heartbeat_payload_valid(p, n));
    p[0] = 0; p[1] = 0; CHECK(!oft_p3_control_heartbeat_payload_valid(p, 2));
    fill(p, 0, 1);
    const size_t fixed[] = {0, 1, 2, 3, 5, 6};
    for (size_t i = 0; i < sizeof(fixed) / sizeof(fixed[0]); ++i) {
        uint8_t saved = p[fixed[i]];
        p[fixed[i]] ^= 0xff;
        CHECK(!oft_p3_control_heartbeat_payload_valid(p, 8));
        p[fixed[i]] = saved;
    }
    fill(p, 2, 1); CHECK(!oft_p3_control_heartbeat_payload_valid(p, 8));
    fill(p, 0xff, 1); CHECK(!oft_p3_control_heartbeat_payload_valid(p, 8));
    fill(p, 0, 3); CHECK(!oft_p3_control_heartbeat_payload_valid(p, 8));
    fill(p, 0, 0xff); CHECK(!oft_p3_control_heartbeat_payload_valid(p, 8));
    const uint8_t reversed[] = {0, 1, 5, 1, 1, 4, 1, 0};
    CHECK(!oft_p3_control_heartbeat_payload_valid(reversed, sizeof(reversed)));
    const uint8_t repeated_tilt[] = {0, 1, 4, 1, 0, 4, 1, 1};
    CHECK(!oft_p3_control_heartbeat_payload_valid(repeated_tilt, sizeof(repeated_tilt)));
    const uint8_t repeated_speed[] = {0, 1, 5, 1, 0, 5, 1, 1};
    CHECK(!oft_p3_control_heartbeat_payload_valid(repeated_speed, sizeof(repeated_speed)));
    puts("Pocket 3 heartbeat contract passed");
    return 0;
}
''', encoding="utf-8")
binary = output / "contract"
subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-ffunction-sections", "-fdata-sections", "-I", str(component / "include"),
                str(source), str(component / "oft_pocket3.c"), "-Wl,--gc-sections",
                "-lm", "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
