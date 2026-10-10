#!/usr/bin/env python3
import os
import re
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "firmware" / "esp_mosaico" / "main"
PROJECT = ROOT / "firmware" / "esp_mosaico"
ARTIFACTS = ROOT / "artifacts" / "mosaico" / "board-contract"

REVISIONS = {
    "v1.0": {
        "config": "CONFIG_OFT_MOSAICO_BOARD_V1_0",
        "name": "ESP-Mosaico V1.0",
        "i2c_sda": 0,
        "i2c_scl": 1,
        "lcd_sclk": 44,
        "lcd_rst": 42,
    },
    "v1.2": {
        "config": "CONFIG_OFT_MOSAICO_BOARD_V1_2",
        "name": "ESP-Mosaico V1.2",
        "i2c_sda": 56,
        "i2c_scl": 3,
        "lcd_sclk": 42,
        "lcd_rst": 44,
    },
}


def run(cmd, *, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def write_fixture(name, sdkconfig_text, source_text=None):
    case_dir = ARTIFACTS / name
    include_dir = case_dir / "include"
    include_dir.mkdir(parents=True, exist_ok=True)
    (include_dir / "sdkconfig.h").write_text(sdkconfig_text, encoding="utf-8")
    if source_text is None:
        source_text = textwrap.dedent(
            """
            #include "oft_board_pins.h"
            #if OFT_BOARD_I2C_SDA < 0 || OFT_BOARD_I2C_SCL < 0
            #error "invalid i2c pins"
            #endif
            int main(void) { return OFT_BOARD_LCD_SCLK + OFT_BOARD_LCD_RST; }
            """
        ).strip()
    source = case_dir / "probe.c"
    source.write_text(source_text + "\n", encoding="utf-8")
    return case_dir, include_dir, source


def compile_header(name, sdkconfig_text):
    case_dir, include_dir, source = write_fixture(name, sdkconfig_text)
    out = case_dir / "probe"
    result = run(
        [
            "gcc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{include_dir}",
            f"-I{MAIN}",
            str(source),
            "-o",
            str(out),
        ]
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return out


def preprocess_macros(name, sdkconfig_text):
    case_dir, include_dir, source = write_fixture(
        name,
        sdkconfig_text,
        '#include "oft_board_pins.h"',
    )
    result = run(["gcc", "-E", "-dM", f"-I{include_dir}", f"-I{MAIN}", str(source)])
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    macros = {}
    for line in result.stdout.splitlines():
        match = re.match(r"#define (OFT_BOARD_[A-Z0-9_]+) (.+)", line)
        if match:
            macros[match.group(1)] = match.group(2).strip()
    return macros


def sdkconfig_for(config):
    return f"#define {config} 1\n"


def check_revision_header(revision, expected):
    macros = preprocess_macros(revision, sdkconfig_for(expected["config"]))
    assert macros["OFT_BOARD_NAME"] == f'"{expected["name"]}"'
    assert int(macros["OFT_BOARD_I2C_SDA"]) == expected["i2c_sda"]
    assert int(macros["OFT_BOARD_I2C_SCL"]) == expected["i2c_scl"]
    assert int(macros["OFT_BOARD_LCD_SCLK"]) == expected["lcd_sclk"]
    assert int(macros["OFT_BOARD_LCD_RST"]) == expected["lcd_rst"]
    compile_header(revision, sdkconfig_for(expected["config"]))


def check_conflicting_revision_rejected():
    case_dir, include_dir, source = write_fixture(
        "conflict",
        "#define CONFIG_OFT_MOSAICO_BOARD_V1_0 1\n#define CONFIG_OFT_MOSAICO_BOARD_V1_2 1\n",
    )
    result = run(["gcc", "-std=c11", f"-I{include_dir}", f"-I{MAIN}", str(source), "-o", str(case_dir / "probe")])
    assert result.returncode != 0
    assert "Exactly one Mosaico board revision" in result.stderr


def check_defaults_select_revision():
    defaults = (PROJECT / "sdkconfig.mosaico-v1.2.defaults").read_text(encoding="utf-8")
    assert "CONFIG_OFT_MOSAICO_BOARD_V1_2=y" in defaults
    assert "CONFIG_OFT_MOSAICO_BOARD_V1_0=y" not in defaults


def check_kconfig_default():
    kconfig = (MAIN / "Kconfig.projbuild").read_text(encoding="utf-8")
    assert re.search(r"choice\s+OFT_MOSAICO_BOARD_REVISION", kconfig)
    assert re.search(r"choice\s+OFT_MOSAICO_BOARD_REVISION[\s\S]*?default\s+OFT_MOSAICO_BOARD_V1_0", kconfig)
    assert "config OFT_MOSAICO_BOARD_V1_2" in kconfig


def check_board_c_uses_contract_pins():
    source = (MAIN / "oft_board.c").read_text(encoding="utf-8")
    assert '#include "oft_board_pins.h"' in source
    required = [
        "OFT_BOARD_NAME",
        "OFT_BOARD_I2C_SDA",
        "OFT_BOARD_I2C_SCL",
        "OFT_BOARD_LCD_SCLK",
        "OFT_BOARD_LCD_RST",
    ]
    for macro in required:
        assert macro in source
    assert ".sda_io_num=OFT_BOARD_I2C_SDA" in source
    assert ".scl_io_num=OFT_BOARD_I2C_SCL" in source
    assert "CO5300_PANEL_BUS_QSPI_CONFIG(OFT_BOARD_LCD_SCLK" in source
    assert ".reset_gpio_num=OFT_BOARD_LCD_RST" in source
    assert "board=%s" in source


def check_no_v12_removed_outputs():
    source = (MAIN / "oft_board.c").read_text(encoding="utf-8")
    assert "1ULL<<56" not in source
    assert "gpio_set_level(56" not in source
    assert "GPIO_NUM_56" not in source
    assert "GPIO_NUM_3" not in source


def main():
    os.environ.pop("CFLAGS", None)
    os.environ.pop("CPPFLAGS", None)
    for revision, expected in REVISIONS.items():
        check_revision_header(revision, expected)
    check_conflicting_revision_rejected()
    check_defaults_select_revision()
    check_kconfig_default()
    check_board_c_uses_contract_pins()
    check_no_v12_removed_outputs()
    print("board revision contract ok")


if __name__ == "__main__":
    main()
