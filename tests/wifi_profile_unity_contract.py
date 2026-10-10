"""Run the board Wi-Fi profile tests with the firmware's 64-bit-disabled Unity mode."""
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: wifi_profile_unity_contract.py ESP_IDF_PATH")
root = Path(__file__).resolve().parents[1]
component = root / "firmware/esp_mosaico/components/oft_protocol"
unity = Path(sys.argv[1]).resolve() / "components/unity/unity/src"
assert (unity / "unity.c").is_file()
output = root / "artifacts/mosaico/wifi-profile-unity-contract"
output.mkdir(parents=True, exist_ok=True)
source = output / "runner.c"
source.write_text('''#include "unity.h"
#ifdef UNITY_SUPPORT_64
#error "This harness requires disabled 64-bit Unity assertions"
#endif
void oft_wifi_profile_selftests(void);
void setUp(void) {}
void tearDown(void) {}
int main(void) {
    UNITY_BEGIN();
    oft_wifi_profile_selftests();
    return UNITY_END();
}
''', encoding="utf-8")
binary = output / "contract"
subprocess.run(["gcc", "-std=c11", "-DUNITY_INT_WIDTH=32", "-DUNITY_LONG_WIDTH=32",
                "-DUNITY_POINTER_WIDTH=32", "-I", str(unity),
                "-I", str(component / "include"), str(source), str(unity / "unity.c"),
                str(component / "test/test_wifi_profile.c"),
                *[str(p) for p in sorted(component.glob("*.c"))],
                "-lm", "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
