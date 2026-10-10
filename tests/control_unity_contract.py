"""Run the existing control Unity cases with the same host harness/profile."""
from pathlib import Path

runner = Path(__file__).with_name("wifi_profile_unity_contract.py")
source = runner.read_text(encoding="utf-8")
source = source.replace("wifi-profile-unity-contract", "control-profile-unity-contract")
source = source.replace("oft_wifi_profile_selftests", "oft_control_selftests")
source = source.replace("test_wifi_profile.c", "test_control.c")
exec(compile(source, str(runner), "exec"), {"__file__": str(runner), "__name__": "__main__"})
