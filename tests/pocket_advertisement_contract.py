"""Exercise the production Pocket 3 filter against captured and invalid adverts."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
component = root / "firmware/esp_mosaico/components/oft_protocol"
output = root / "artifacts/mosaico/advertisement-contract"
output.mkdir(parents=True, exist_ok=True)
source = output / "contract.c"
source.write_text(r'''
#include <stdio.h>
#include "oft_pocket3.h"
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); return 1; } } while (0)
int main(void) {
    /* 2026-10-09 capture: aa 08 20 00 40 followed by a six-byte identity.
       The identity below is synthetic; no private device address is stored. */
    uint8_t p[11] = {0xaa, 0x08, 0x20, 0x00, 0x40, 1, 2, 3, 4, 5, 6};
    CHECK(oft_p3_advertisement(p, sizeof(p)));
    p[4] = 0x00; CHECK(oft_p3_advertisement(p, sizeof(p)));
    p[4] = 0x80; CHECK(oft_p3_advertisement(p, sizeof(p)));
    p[4] = 0xc0; CHECK(oft_p3_advertisement(p, sizeof(p)));
    p[4] = 0x40;
    for (size_t n = 0; n < sizeof(p); ++n) CHECK(!oft_p3_advertisement(p, n));
    CHECK(!oft_p3_advertisement(NULL, sizeof(p)));
    p[0] = 0xab; CHECK(!oft_p3_advertisement(p, sizeof(p))); p[0] = 0xaa;
    p[1] = 0x09; CHECK(!oft_p3_advertisement(p, sizeof(p))); p[1] = 0x08;
    p[2] = 0x21; CHECK(!oft_p3_advertisement(p, sizeof(p)));
    p[2] = 0x22; CHECK(!oft_p3_advertisement(p, sizeof(p))); p[2] = 0x20;
    p[3] = 1; CHECK(!oft_p3_advertisement(p, sizeof(p))); p[3] = 0;
    const uint8_t unknown[] = {1, 0x20, 0x41, 0x7f, 0x81, 0xff};
    for (size_t i = 0; i < sizeof(unknown); ++i) {
        p[4] = unknown[i]; CHECK(!oft_p3_advertisement(p, sizeof(p)));
    }
    puts("Pocket 3 advertisement contract passed");
    return 0;
}
''', encoding="utf-8")
binary = output / "contract"
subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-ffunction-sections", "-fdata-sections", "-I", str(component / "include"),
                str(source), str(component / "oft_pocket3.c"), "-Wl,--gc-sections",
                "-lm", "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
