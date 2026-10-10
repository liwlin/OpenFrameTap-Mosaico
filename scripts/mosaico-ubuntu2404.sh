#!/usr/bin/env bash
# Build and inspect only. Invoke explicitly with wsl.exe -d Ubuntu2404.
set -euo pipefail

task_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
task_sdk=${MOSAICO_IDF_PATH:-${IDF_PATH:-$HOME/esp/esp-idf}}
[[ -f "$task_sdk/export.sh" ]] || {
    printf 'Set MOSAICO_IDF_PATH to the pinned ESP-IDF checkout.\n' >&2
    exit 1
}
task_expected_sdk=812f3e98ca5da31ed4fc6be8b703019f7b6dcaa6
task_project="$task_root/firmware/esp_mosaico"
task_board=${MOSAICO_BOARD:-v1.0}
task_output="$task_root/artifacts/mosaico/ubuntu2404"
task_defaults="$task_project/sdkconfig.defaults"
case "$task_board" in
    v1.0) ;;
    v1.2)
        task_output="$task_output/v1.2"
        task_defaults="$task_defaults;$task_project/sdkconfig.mosaico-v1.2.defaults"
        ;;
    *) printf 'Unsupported MOSAICO_BOARD: %s\n' "$task_board" >&2; exit 1 ;;
esac
task_build="$task_output/build"
mkdir -p "$task_output/logs"
task_log="$task_output/logs/$(date -u +%Y%m%dT%H%M%S-%N)-build.log"
exec > >(tee "$task_log") 2>&1
trap 'task_code=$?; printf "Mosaico build exit=%s log=%s\n" "$task_code" "$task_log"' EXIT

[[ ${WSL_DISTRO_NAME:-} == Ubuntu2404 ]] || {
    printf 'Use wsl.exe -d Ubuntu2404 -- /bin/bash <this-script>\n' >&2
    exit 1
}
export PYTHONDONTWRITEBYTECODE=1 GIT_OPTIONAL_LOCKS=0
[[ $(git -C "$task_sdk" rev-parse HEAD) == "$task_expected_sdk" ]] || {
    printf 'Shared SDK commit differs from the approved baseline.\n' >&2
    exit 1
}
[[ -z $(git -C "$task_sdk" status --porcelain) ]] || {
    printf 'Shared SDK has local changes; preserving it and stopping.\n' >&2
    exit 1
}
task_vendor="$task_project/components/oft_openh264/vendor"
task_expected_vendor=$(git -C "$task_root" ls-tree HEAD firmware/esp_mosaico/components/oft_openh264/vendor | awk '{print $3}')
[[ $(git -C "$task_vendor" rev-parse HEAD) == "$task_expected_vendor" ]] || {
    printf 'Initialize the pinned OpenH264 submodule before building.\n' >&2
    exit 1
}
[[ -z $(git -C "$task_vendor" status --porcelain) ]] || {
    printf 'OpenH264 has local changes; preserving it and stopping.\n' >&2
    exit 1
}
# Do not silently inherit experimental decode/benchmark settings.
if compgen -e | grep -q '^OFT_'; then
    printf 'Unset experimental OFT_* environment variables before this baseline build.\n' >&2
    exit 1
fi
task_lock_before=$(sha256sum "$task_project/dependencies.lock" | awk '{print $1}')
task_defaults_before=$(sha256sum "$task_project/sdkconfig.defaults" | awk '{print $1}')
task_profile_before=''
if [[ "$task_board" == v1.2 ]]; then
    task_profile_before=$(sha256sum "$task_project/sdkconfig.mosaico-v1.2.defaults" | awk '{print $1}')
fi
mkdir -p "$task_output/inputs"
cp "$task_project/dependencies.lock" "$task_project/sdkconfig.defaults" \
    "$task_project/partitions.csv" "$task_output/inputs/"
if [[ "$task_board" == v1.2 ]]; then
    cp "$task_project/sdkconfig.mosaico-v1.2.defaults" "$task_output/inputs/"
fi
source "$task_sdk/export.sh"
[[ $(idf.py --version) == 'ESP-IDF v6.1.0' ]]
export IDF_PY_BUILD_JOBS=2 CMAKE_BUILD_PARALLEL_LEVEL=1
export PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
printf 'distro=%s board=%s sdk=%s source=%s openh264=%s\n' \
    "$WSL_DISTRO_NAME" "$task_board" "$task_expected_sdk" "$(git -C "$task_root" rev-parse HEAD)" "$task_expected_vendor"
python --version
riscv32-esp-elf-gcc --version
cmake --version
ninja --version
git -C "$task_root" submodule status --recursive
git -C "$task_sdk" submodule status --recursive > "$task_output/inputs/sdk-submodules.txt"
mkdir -p "$task_build"
idf.py --preview -C "$task_project" -B "$task_build" \
    -D IDF_TARGET=esp32s31 \
    -D "SDKCONFIG=$task_build/sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$task_defaults" reconfigure build
[[ $(sha256sum "$task_project/dependencies.lock" | awk '{print $1}') == "$task_lock_before" ]]
[[ $(sha256sum "$task_project/sdkconfig.defaults" | awk '{print $1}') == "$task_defaults_before" ]]
if [[ "$task_board" == v1.2 ]]; then
    [[ $(sha256sum "$task_project/sdkconfig.mosaico-v1.2.defaults" | awk '{print $1}') == "$task_profile_before" ]]
fi
[[ $(git -C "$task_sdk" rev-parse HEAD) == "$task_expected_sdk" ]]
[[ -z $(git -C "$task_sdk" status --porcelain) ]]
python "$task_root/scripts/mosaico-verify-build.py" "$task_build" "$task_root" "$task_sdk" "$task_board"
printf 'Verified artifacts: %s/artifacts.json\n' "$task_output"
printf 'Build only: identify Mosaico and verify factory layout before application-only flashing.\n'
