# Ubuntu2404 / WSL 构建

本分支的构建验证环境为 Ubuntu 24.04（WSL 发行版名称 `Ubuntu2404`）。
脚本只构建和离线检查，不烧录、控制相机或修改共享 SDK。

## 固定输入

| 输入 | 版本 |
| --- | --- |
| ESP-IDF | v6.1.0 preview / `812f3e98ca5da31ed4fc6be8b703019f7b6dcaa6` |
| 芯片 | `esp32s31`，不能替换为 `esp32s3` |
| OpenH264 | v2.6.0 / `652bdb7719f30b52b08e506645a7322ff1b2cc6f` |
| 组件 | `firmware/esp_mosaico/dependencies.lock` |
| 并发 | 外层 2 任务，嵌套构建 1 任务 |

准备与该 SDK 匹配的工具链及 Python 环境，并初始化仓库子模块。
在 Ubuntu2404 内的仓库根目录运行：

```sh
git submodule update --init --recursive
export MOSAICO_IDF_PATH=/path/to/pinned/esp-idf
MOSAICO_BOARD=v1.2 bash scripts/mosaico-ubuntu2404.sh
```

SDK 路径依次取 `MOSAICO_IDF_PATH`、`IDF_PATH`、`$HOME/esp/esp-idf`。
路径可配置，但 SDK commit、clean-tree 和厂商子模块检查保持强制。
V1.0 使用 `MOSAICO_BOARD=v1.0`；本次 Release 仅交付 V1.2 预编译应用。

## 产物与校验

V1.2 产物根为 `artifacts/mosaico/ubuntu2404/v1.2/`：

- `build/openframetap_mosaico.bin`：应用镜像。
- `build/*.elf` / `*.map`：本地调试资料，不作为普通安装文件。
- `logs/`：构建输出；`inputs/`：固定输入快照。
- `artifacts.json`：完整本机验证清单，包含本地路径，不能直接公开。

校验器检查实际 target、板型引脚、关键配置、PSRAM XIP、分区 MD5、应用地址及镜像 SHA256。
脚本拒绝继承 `OFT_*` 实验环境变量，不自动升级依赖或修改 SDK。
构建工具打印的通用 `idf.py flash` / 全量烧录示例不适用于本设备；只按 [V1.2 更新边界](mosaico-v1.2.md) 处理应用分区。

## 主机回归

在 SDK 路径正确的 Ubuntu2404 中执行 `tests/` 下的独立 Python 合同测试。
`wifi_profile_unity_contract.py` 需额外传入 SDK 路径，以使用实际 Unity 头文件。
这些测试会在忽略的 artifacts 目录生成小型主机程序；不使用原 Linux 项目的 pytest 套件。
编译、主机测试、板端自检和物理动作验收是不同层次，见 [验证矩阵](mosaico-full-bench.md)。
