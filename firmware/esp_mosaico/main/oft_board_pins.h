#pragma once

#include "sdkconfig.h"

#if defined(CONFIG_OFT_MOSAICO_BOARD_V1_0) && defined(CONFIG_OFT_MOSAICO_BOARD_V1_2)
#error "Exactly one Mosaico board revision must be selected"
#endif

#if defined(CONFIG_OFT_MOSAICO_BOARD_V1_2)
#define OFT_BOARD_NAME "ESP-Mosaico V1.2"
#define OFT_BOARD_I2C_SDA 56
#define OFT_BOARD_I2C_SCL 3
#define OFT_BOARD_LCD_SCLK 42
#define OFT_BOARD_LCD_RST 44
#else
#define OFT_BOARD_NAME "ESP-Mosaico V1.0"
#define OFT_BOARD_I2C_SDA 0
#define OFT_BOARD_I2C_SCL 1
#define OFT_BOARD_LCD_SCLK 44
#define OFT_BOARD_LCD_RST 42
#endif
