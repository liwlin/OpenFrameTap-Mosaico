# ESP-Mosaico V1.2 适配

本分支在保留 V1.0 配置的基础上增加显式 V1.2 板型。
硬件差异依据 [Espressif Mosaico 指南](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s31/esp-mosaico/user_guide.html)。

| 信号 | V1.0 | V1.2 |
| --- | --- | --- |
| 内部 I2C SDA | GPIO0 | GPIO56 |
| 内部 I2C SCL | GPIO1 | GPIO3 |
| LCD QSPI SCLK | GPIO44 | GPIO42 |
| LCD RST | GPIO42 | GPIO44 |

V1.2 的 GPIO0/1 属于外部模块 I2C；不要用它们访问板载触摸、IMU 和电量计。
LCD 数据、CS、触摸中断、Function Button、振动马达及 GPIO60 供电控制保留共同定义。
不改动 GPIO57、OTP、充电器硬件或 NAND。

## 构建

在 Ubuntu2404 / WSL 的项目根目录：

```sh
export MOSAICO_IDF_PATH=/path/to/pinned/esp-idf
MOSAICO_BOARD=v1.2 bash scripts/mosaico-ubuntu2404.sh
```

产物位于 `artifacts/mosaico/ubuntu2404/v1.2/`。
脚本核对固定 SDK、子模块、依赖锁和实际预处理后的板级引脚，最多使用两个外层编译任务。
V1.2 使用已在本机验证的 PSRAM XIP、200MHz PSRAM、DIO/80MHz NOR 配置。
该启动路径有实机证据；旧 Flash 执行路径失败的完整底层原因尚未确定，不据此修改工厂 bootloader。

## 应用更新

发布二进制仅用于已核对的 Mosaico V1.2。必须在目标设备上独立核实：

- 芯片确为 ESP32-S31，NOR 为 16MB，安全配置允许该镜像。
- 独立读取 `0x9000` 处的实际分区表，确认应用起点为 `0x20000` 且应用容量及擦除边界足够。
- 项目构建 CSV 的应用容量为 `0x680000`；本机经专项核对保留的原厂 factory 容量为 `0x7d0000`，其他分区也有差异。构建表不能代替目标设备实际布局，更不能直接写入覆盖原厂表。
- 保存保护前缀以及本次实际擦除范围的原始应用备份，再执行应用区更新。
- 写后完整读回镜像并比较保护前缀，再复位验证。

本次 Release 应用的擦除覆盖为 `0x23c000` 字节，从 `0x20000` 起。
不同版本须按镜像长度向 4KiB 对齐重新计算。后续镜像扩大时，在首次覆盖前补齐原厂尾部；不能把已被项目固件覆盖的数据当作原厂备份。

保留 bootloader、分区表、NVS、其他 NOR 分区及 NAND；不使用全片擦除或通用合并镜像。
本机恢复文件具有设备身份，不能作为别人的原厂镜像分发。
当前验证与剩余问题见 [发布验证记录](mosaico-full-bench.md)。
