#pragma once
/* Initial compressed input capacity per AU. OpenH264 retains its three-AU
   reserve and native growth checks; this is not a hard decoder memory cap. */
#define OFT_H264_INPUT_CAPACITY (256 * 1024)
