"""Inspect Mosaico build artifacts offline; never access a serial device."""
import csv
import hashlib
import json
import os
import re
import shlex
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def config(path):
    return dict(re.findall(r"^(CONFIG_\w+)=(.*)$", path.read_text(), re.MULTILINE))


def main():
    require(len(sys.argv) in (4, 5), "Usage: verifier BUILD ROOT SDK [v1.0|v1.2]")
    build, root, sdk = (Path(arg).resolve() for arg in sys.argv[1:4])
    board = sys.argv[4] if len(sys.argv) == 5 else "v1.0"
    require(board in ("v1.0", "v1.2"), "Unsupported Mosaico board revision")
    distro = os.environ.get("WSL_DISTRO_NAME")
    require(distro == "Ubuntu2404", "Run the verifier in Ubuntu2404")
    project = root / "firmware/esp_mosaico"
    output = build.parent
    actual = config(build / "sdkconfig")
    defaults = config(project / "sdkconfig.defaults")
    require(actual.get("CONFIG_IDF_TARGET") == '"esp32s31"', "Wrong chip target")
    board_key = "CONFIG_OFT_MOSAICO_BOARD_" + board.upper().replace(".", "_")
    require(actual.get(board_key) == "y", "Configured board revision differs from selected profile")
    macros = subprocess.check_output(
        ["riscv32-esp-elf-gcc", "-E", "-dM", "-x", "c", "-I", str(build / "config"),
         "-I", str(project / "main"), "-include", "oft_board_pins.h", "/dev/null"], text=True,
    )
    expected_pins = {"v1.0": (0, 1, 44, 42), "v1.2": (56, 3, 42, 44)}[board]
    pin_keys = ("OFT_BOARD_I2C_SDA", "OFT_BOARD_I2C_SCL", "OFT_BOARD_LCD_SCLK", "OFT_BOARD_LCD_RST")
    selected_pins = {}
    for name, expected_pin in zip(pin_keys, expected_pins):
        match = re.search(r"^#define " + name + r"\s+(\d+)\s*$", macros, re.MULTILINE)
        require(match is not None and int(match.group(1)) == expected_pin, "Wrong resolved board pin: " + name)
        selected_pins[name] = int(match.group(1))
    critical = [
        "CONFIG_ESPTOOLPY_FLASHSIZE_16MB", "CONFIG_PARTITION_TABLE_CUSTOM",
        "CONFIG_PARTITION_TABLE_OFFSET", "CONFIG_PARTITION_TABLE_CUSTOM_FILENAME",
        "CONFIG_LWIP_UDP_RECVMBOX_SIZE", "CONFIG_LWIP_TCPIP_RECVMBOX_SIZE",
        "CONFIG_SPIRAM", "CONFIG_SPIRAM_MODE_OCT", "CONFIG_SPIRAM_SPEED_200M",
        "CONFIG_SPIRAM_MEMTEST", "CONFIG_SPIRAM_MALLOC_RESERVE_INTERNAL",
        "CONFIG_ESP_MAIN_TASK_STACK_SIZE", "CONFIG_BT_NIMBLE_ENABLED",
    ]
    for key in critical:
        require(actual.get(key) == defaults.get(key), f"Configuration mismatch: {key}")
    if board == "v1.2":
        for key in ("CONFIG_SPIRAM_XIP_FROM_PSRAM", "CONFIG_SPIRAM_FETCH_INSTRUCTIONS",
                    "CONFIG_SPIRAM_RODATA", "CONFIG_SPIRAM_FLASH_LOAD_TO_PSRAM"):
            require(actual.get(key) == "y", f"V1.2 requires the validated PSRAM execution path: {key}")
            critical.append(key)
        for key, value in {"CONFIG_SPIRAM_IGNORE_NOTFOUND": "n",
                           "CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP": "y",
                           "CONFIG_ESP_WIFI_STATIC_TX_BUFFER": "y",
                           "CONFIG_ESP_WIFI_STATIC_TX_BUFFER_NUM": "16",
                           "CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM": "32"}.items():
            require(actual.get(key, "n") == value, f"V1.2 Wi-Fi PSRAM path mismatch: {key}")
            critical.append(key)
    description = json.loads((build / "project_description.json").read_text())
    require(description["target"] == "esp32s31", "Project description target mismatch")
    require(description["project_name"] == "openframetap_mosaico", "Wrong project")
    compile_commands = (build / "compile_commands.json").read_text()
    experimental_definitions = (
        "OFT_CABAC32", "OFT_CABAC_IRAM", "OFT_RESIDUAL_IRAM", "OFT_BENCH_EMBEDDED",
    )
    for name in experimental_definitions:
        require(f"-D{name}" not in compile_commands, f"Experimental build definition: {name}")
    flash = json.loads((build / "flasher_args.json").read_text())
    require(flash["extra_esptool_args"]["chip"] == "esp32s31", "Flash target mismatch")
    require(flash["flash_files"].get("0x20000") == "openframetap_mosaico.bin", "App offset mismatch")
    require(flash["flash_files"].get("0x9000") == "partition_table/partition-table.bin", "Partition offset mismatch")
    app_args = (build / "app-flash_args").read_text()
    images = [shlex.split(line) for line in app_args.splitlines() if line.startswith("0x")]
    require(images == [["0x20000", "openframetap_mosaico.bin"]], "App flash must contain only the application")

    table_data = (build / "partition_table/partition-table.bin").read_bytes()
    rows = []
    md5_ok = False
    for offset in range(0, len(table_data), 32):
        entry = table_data[offset:offset + 32]
        if entry[:2] == b"\xeb\xeb":
            md5_ok = entry[16:] == hashlib.md5(table_data[:offset]).digest()
            break
        require(entry[:2] == b"\xaa\x50", "Invalid partition entry")
        _, kind, subtype, address, size, name, flags = struct.unpack("<HBBII16sI", entry)
        rows.append({"name": name.rstrip(b"\0").decode("ascii"), "type": kind,
                     "subtype": subtype, "offset": address, "size": size, "flags": flags})
    require(md5_ok, "Partition table MD5 mismatch")
    expected = []
    types = {"app": 0, "data": 1}
    subtypes = {"nvs": 2, "ota": 0, "phy": 1, "factory": 0}
    for line in (project / "partitions.csv").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, kind, subtype, address, size, flags = [value.strip() for value in next(csv.reader([line]))]
        expected.append({"name": name, "type": types[kind],
                         "subtype": subtypes[subtype] if subtype in subtypes else int(subtype, 0),
                         "offset": int(address, 0), "size": int(size, 0), "flags": 0})
        require(not flags, "Unexpected partition flags")
    require(rows == expected, "Generated partitions differ from the source layout")
    factory = next(row for row in rows if row["name"] == "factory")
    app = build / "openframetap_mosaico.bin"
    require(app.stat().st_size <= factory["size"], "Application exceeds factory partition")

    # esptool validates the image checksum and appended SHA256 independently.
    from esptool.targets import CHIP_DEFS
    expected_chip_id = CHIP_DEFS["esp32s31"].IMAGE_CHIP_ID
    image_checks = {}
    for filename in ("openframetap_mosaico.bin", "bootloader/bootloader.bin"):
        data = (build / filename).read_bytes()
        require(data[0] == 0xE9 and struct.unpack_from("<H", data, 12)[0] == expected_chip_id,
                f"Image chip header mismatch: {filename}")
        if board == "v1.2" and filename == "openframetap_mosaico.bin":
            offset = 24
            segment_addresses = []
            for _ in range(data[1]):
                address, size = struct.unpack_from("<II", data, offset)
                segment_addresses.append(address)
                offset += 8 + size
                require(offset <= len(data), "Application segment extends beyond image")
            require(sum(0x50000000 <= address < 0x54000000 for address in segment_addresses) == 2,
                    "V1.2 text and rodata must both map to PSRAM")
            require(not any(0x40000000 <= address < 0x44000000 for address in segment_addresses),
                    "Unexpected Flash execution segment in V1.2 application")
        info = subprocess.check_output(
            [sys.executable, "-m", "esptool", "--chip", "esp32s31", "image-info", str(build / filename)],
            text=True,
        )
        require(info.count("(valid)") >= 2, f"Image checksum/hash unverified: {filename}")
        image_checks[filename] = info
        print(info)
    paths = ["openframetap_mosaico.bin", "openframetap_mosaico.elf", "openframetap_mosaico.map",
             "bootloader/bootloader.bin", "partition_table/partition-table.bin",
             "app-flash_args", "flasher_args.json", "sdkconfig", "compile_commands.json"]
    manifest = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "distro": distro, "target": "esp32s31", "board_revision": board,
        "resolved_board_pins": selected_pins, "build_directory": str(build),
        "source_commit": git(root, "rev-parse", "HEAD"),
        "source_status": git(root, "status", "--short"),
        "sdk_commit": git(sdk, "rev-parse", "HEAD"),
        "sdk_version": subprocess.check_output(["idf.py", "--version"], text=True).strip(),
        "python_version": sys.version,
        "compiler": subprocess.check_output(["riscv32-esp-elf-gcc", "--version"], text=True).splitlines()[0],
        "submodules": git(root, "submodule", "status", "--recursive"),
        "dependencies_lock_sha256": sha256(project / "dependencies.lock"),
        "sdkconfig_defaults_sha256": sha256(project / "sdkconfig.defaults"),
        "board_profile_defaults_sha256": sha256(project / "sdkconfig.mosaico-v1.2.defaults") if board == "v1.2" else None,
        "board_pin_header_sha256": sha256(project / "main/oft_board_pins.h"),
        "board_source_sha256": {name: sha256(project / name) for name in
                                ("main/oft_board.c", "main/oft_board_pins.h", "main/Kconfig.projbuild")},
        "checked_configuration": {key: actual.get(key, "n") for key in critical},
        "experimental_compile_definitions_absent": list(experimental_definitions),
        "partition_table_md5_valid": md5_ok, "partitions": rows,
        "application_partition": {"offset": "0x20000", "size": "0x680000",
                                  "free_bytes": factory["size"] - app.stat().st_size},
        "files": {name: {"bytes": (build / name).stat().st_size,
                         "sha256": sha256(build / name)} for name in paths},
        "entrypoint_sha256": sha256(root / "scripts/mosaico-ubuntu2404.sh"),
        "verifier_sha256": sha256(root / "scripts/mosaico-verify-build.py"),
        "image_checks": image_checks,
        "device_flashed": False, "on_device_tests_run": False, "pocket3_tests_run": False,
    }
    (output / "artifacts.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"verified": True, "app_bytes": app.stat().st_size,
                      "app_sha256": sha256(app), "partition_md5": md5_ok,
                      "manifest": str(output / "artifacts.json")}, indent=2))


if __name__ == "__main__":
    main()
