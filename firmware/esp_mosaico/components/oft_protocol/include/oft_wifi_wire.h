#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "oft_duml.h"

/* Bounded wire codec, not a socket. One session owner serializes all calls. */
#define OFT_WIFI_DATAGRAM_MAX 4095
typedef struct {
    uint16_t session, sequence;
    uint8_t type;
    const uint8_t *raw;
    size_t size;
} oft_wifi_packet_t;
typedef struct {
    uint16_t session, next_sequence, last_sent, peer, media_received, reply_received;
    uint8_t message_counter;
    bool have_media, have_reply, have_status;
} oft_wifi_session_t;
typedef enum {
    OFT_WIFI_ACK_SEND_OK,
    OFT_WIFI_ACK_SEND_RETRY,
    OFT_WIFI_ACK_SEND_FATAL
} oft_wifi_ack_send_result_t;
typedef enum {
    OFT_WIFI_ACK_IDLE,
    OFT_WIFI_ACK_SENT,
    OFT_WIFI_ACK_DEFERRED,
    OFT_WIFI_ACK_FAILED
} oft_wifi_ack_step_result_t;
typedef struct {
    bool retrying;
    int64_t first_failure_us;
    int64_t next_due_us;
} oft_wifi_ack_tx_t;
typedef oft_wifi_ack_send_result_t (*oft_wifi_ack_send_fn)(const uint8_t *raw,size_t size,void *ctx);

bool oft_wifi_parse(const uint8_t *raw,size_t size,oft_wifi_packet_t *packet);
bool oft_wifi_direct_duml(const oft_wifi_packet_t *packet,oft_duml_frame_t *frame);
bool oft_wifi_init(oft_wifi_session_t *s,uint16_t session,uint16_t seed);
size_t oft_wifi_handshake(const oft_wifi_session_t *s,uint8_t *out,size_t capacity);
bool oft_wifi_handshake_accepted(const oft_wifi_session_t *s,const uint8_t *raw,size_t size);
/* Validates current-session status; never advances peer from WhType 02/03. */
bool oft_wifi_observe(oft_wifi_session_t *s,const uint8_t *raw,size_t size);
size_t oft_wifi_ack(const oft_wifi_session_t *s,uint8_t *out,size_t capacity);
oft_wifi_ack_send_result_t oft_wifi_ack_classify_send(int sent,int error);
oft_wifi_ack_step_result_t oft_wifi_ack_tx_step(oft_wifi_ack_tx_t *tx,const oft_wifi_session_t *wire,
    int64_t now_us,oft_wifi_ack_send_fn send,void *ctx);
size_t oft_wifi_wrap(oft_wifi_session_t *s,const uint8_t *duml,size_t size,uint8_t *out,size_t capacity);
uint16_t oft_wifi_duml_sequence(uint16_t counter);
typedef struct {uint16_t sequence[4];bool used[4];unsigned next;} oft_wifi_pending_t;
void oft_wifi_pending_add(oft_wifi_pending_t *pending,uint16_t sequence);
bool oft_wifi_pending_take(oft_wifi_pending_t *pending,uint16_t sequence);
