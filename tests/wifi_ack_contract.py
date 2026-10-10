"""Exercise the production Wi-Fi ACK retry helper with host-compiled code."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
component = root / "firmware/esp_mosaico/components/oft_protocol"
output = root / "artifacts/mosaico/wifi-ack-contract"
output.mkdir(parents=True, exist_ok=True)
source = output / "contract.c"
source.write_text(r'''
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "oft_wifi_wire.h"
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); return 1; } } while (0)
static const uint8_t status[] = {
  0x22,0x80,0x55,0x70,0,0,1,0x86,0xa8,0x82,0xa8,0x82,0,0,0,0,
  0xa8,0x82,0xc8,0x82,0,0,0,0,0xd8,0x82,0xd8,0x82,0,0,0,0,0,0};
static const uint8_t expected_ack[] = {
  0x22,0x80,0x55,0x70,0,0,4,0x83,0xa8,0x82,0xa8,0x82,0,0,0,0,
  0xc8,0x82,0xc8,0x82,0,0,0,0,0xd8,0x82,0,0x83,0,0,0,0,0,0};
typedef struct {
    oft_wifi_ack_send_result_t result;
    unsigned calls;
    uint8_t last[40];
    size_t last_size;
} send_ctx_t;
static oft_wifi_ack_send_result_t send_capture(const uint8_t *raw, size_t size, void *opaque) {
    send_ctx_t *ctx = (send_ctx_t *)opaque;
    ctx->calls++;
    ctx->last_size = size;
    if (size <= sizeof(ctx->last)) memcpy(ctx->last, raw, size);
    return ctx->result;
}
static int ready_wire(oft_wifi_session_t *s) {
    CHECK(oft_wifi_init(s, 0x7055, 0x8300));
    s->peer = 0x82d0;
    CHECK(oft_wifi_observe(s, status, sizeof(status)));
    return 0;
}
int main(void) {
    CHECK(oft_wifi_ack_classify_send(34, 0) == OFT_WIFI_ACK_SEND_OK);
    CHECK(oft_wifi_ack_classify_send(-1, ENOMEM) == OFT_WIFI_ACK_SEND_RETRY);
    CHECK(oft_wifi_ack_classify_send(-1, EAGAIN) == OFT_WIFI_ACK_SEND_RETRY);
#if EWOULDBLOCK != EAGAIN
    CHECK(oft_wifi_ack_classify_send(-1, EWOULDBLOCK) == OFT_WIFI_ACK_SEND_RETRY);
#endif
    CHECK(oft_wifi_ack_classify_send(33, 0) == OFT_WIFI_ACK_SEND_FATAL);
    CHECK(oft_wifi_ack_classify_send(-1, EBADF) == OFT_WIFI_ACK_SEND_FATAL);
    CHECK(oft_wifi_ack_classify_send(-1, EINVAL) == OFT_WIFI_ACK_SEND_FATAL);
    CHECK(oft_wifi_ack_classify_send(-1, 0) == OFT_WIFI_ACK_SEND_FATAL);

    oft_wifi_session_t wire;
    CHECK(ready_wire(&wire) == 0);
    oft_wifi_session_t before = wire;
    oft_wifi_ack_tx_t tx = {0};
    send_ctx_t ctx = {.result = OFT_WIFI_ACK_SEND_OK};
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 1000, send_capture, &ctx) == OFT_WIFI_ACK_SENT);
    CHECK(ctx.calls == 1);
    CHECK(ctx.last_size == sizeof(expected_ack));
    CHECK(memcmp(ctx.last, expected_ack, sizeof(expected_ack)) == 0);
    CHECK(memcmp(&wire, &before, sizeof(wire)) == 0);
    CHECK(!tx.retrying && tx.next_due_us == 26000);
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 25999, send_capture, &ctx) == OFT_WIFI_ACK_IDLE);
    CHECK(ctx.calls == 1);
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 26000, send_capture, &ctx) == OFT_WIFI_ACK_SENT);
    CHECK(ctx.calls == 2);

    tx = (oft_wifi_ack_tx_t){0}; ctx = (send_ctx_t){.result = OFT_WIFI_ACK_SEND_RETRY};
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 1000, send_capture, &ctx) == OFT_WIFI_ACK_DEFERRED);
    CHECK(tx.retrying && tx.first_failure_us == 1000 && tx.next_due_us == 6000);
    for (unsigned i = 0; i < 64; ++i) {
        CHECK(oft_wifi_ack_tx_step(&tx, &wire, 1001 + (int64_t)i, send_capture, &ctx) == OFT_WIFI_ACK_IDLE);
    }
    CHECK(ctx.calls == 1);
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 6000, send_capture, &ctx) == OFT_WIFI_ACK_DEFERRED);
    CHECK(ctx.calls == 2);
    CHECK(tx.first_failure_us == 1000 && tx.next_due_us == 11000);
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 101000, send_capture, &ctx) == OFT_WIFI_ACK_FAILED);
    CHECK(ctx.calls == 2);
    tx = (oft_wifi_ack_tx_t){0}; ctx = (send_ctx_t){.result = OFT_WIFI_ACK_SEND_RETRY};
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 5000, send_capture, &ctx) == OFT_WIFI_ACK_DEFERRED);
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 4999, send_capture, &ctx) == OFT_WIFI_ACK_FAILED);
    CHECK(ctx.calls == 1);

    tx = (oft_wifi_ack_tx_t){0}; ctx = (send_ctx_t){.result = OFT_WIFI_ACK_SEND_RETRY};
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 2000, send_capture, &ctx) == OFT_WIFI_ACK_DEFERRED);
    uint8_t stale_ack[34]; memcpy(stale_ack, ctx.last, sizeof(stale_ack));
    wire.media_received += 13; wire.reply_received += 7;
    before = wire;
    ctx.result = OFT_WIFI_ACK_SEND_OK;
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 7000, send_capture, &ctx) == OFT_WIFI_ACK_SENT);
    CHECK(memcmp(ctx.last, stale_ack, sizeof(stale_ack)) != 0);
    CHECK((ctx.last[8] | ((unsigned)ctx.last[9] << 8)) == wire.media_received);
    CHECK((ctx.last[10] | ((unsigned)ctx.last[11] << 8)) == wire.media_received);
    CHECK((ctx.last[16] | ((unsigned)ctx.last[17] << 8)) == wire.reply_received);
    CHECK((ctx.last[18] | ((unsigned)ctx.last[19] << 8)) == wire.reply_received);
    CHECK(memcmp(&wire, &before, sizeof(wire)) == 0);
    CHECK(!tx.retrying && tx.first_failure_us == 0 && tx.next_due_us == 32000);
    ctx.result = OFT_WIFI_ACK_SEND_RETRY;
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 32000, send_capture, &ctx) == OFT_WIFI_ACK_DEFERRED);
    CHECK(tx.retrying && tx.first_failure_us == 32000 && tx.next_due_us == 37000);

    tx = (oft_wifi_ack_tx_t){0}; ctx = (send_ctx_t){.result = OFT_WIFI_ACK_SEND_FATAL};
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 0, send_capture, &ctx) == OFT_WIFI_ACK_FAILED);
    CHECK(oft_wifi_ack_tx_step(NULL, &wire, 0, send_capture, &ctx) == OFT_WIFI_ACK_FAILED);
    CHECK(oft_wifi_ack_tx_step(&tx, NULL, 0, send_capture, &ctx) == OFT_WIFI_ACK_FAILED);
    CHECK(oft_wifi_ack_tx_step(&tx, &wire, 0, NULL, &ctx) == OFT_WIFI_ACK_FAILED);
    oft_wifi_session_t invalid = {0};
    unsigned before_calls = ctx.calls;
    CHECK(oft_wifi_ack_tx_step(&tx, &invalid, 0, send_capture, &ctx) == OFT_WIFI_ACK_FAILED);
    CHECK(ctx.calls == before_calls);
    puts("Wi-Fi ACK contract passed");
    return 0;
}
''', encoding="utf-8")
binary = output / "contract"
subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-ffunction-sections", "-fdata-sections", "-I", str(component / "include"),
                str(source), str(component / "oft_wifi_wire.c"), str(component / "oft_duml.c"),
                "-Wl,--gc-sections", "-lm", "-o", str(binary)], check=True)
subprocess.run([str(binary)], check=True)
