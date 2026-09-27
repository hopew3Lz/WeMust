"""
Bale Tunnel Configuration
=========================
All values can be set two ways:

1. Environment variables (recommended for Railway / Docker / any host
   where you don't want secrets committed to disk) — these always win
   if set.
2. The plaintext defaults below, for quick local testing.

Required environment variables when deploying:
    IRAN_BOT_TOKEN
    FOREIGN_BOT_TOKEN
    UPSTREAM_CHAT_ID
    DOWNSTREAM_CHAT_ID
"""

import os


def _env_int(name: str, default: int | None) -> int | None:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return int(val)


# ── Bale Bots ────────────────────────────────────────────────────────
# Two distinct bots are required: Bale's getUpdates does NOT return a
# bot's own outgoing messages, so each side must poll a bot that the
# OTHER side sends through. Both bots must be admins in both channels.
IRAN_BOT_TOKEN = os.environ.get("IRAN_BOT_TOKEN", "...")
FOREIGN_BOT_TOKEN = os.environ.get("FOREIGN_BOT_TOKEN", "...")

# Channel (or group) chat IDs. Both bots must be admins in both channels.
# Each channel now carries traffic in BOTH directions (forward + reverse);
# routing is done by conn_id inside each TunnelMessage.
UPSTREAM_CHAT_ID = _env_int("UPSTREAM_CHAT_ID", 5941613343)    # iran transmits, foreign reads
DOWNSTREAM_CHAT_ID = _env_int("DOWNSTREAM_CHAT_ID", 5693632721)  # foreign transmits, iran reads

BALE_API_BASE = os.environ.get("BALE_API_BASE", "https://tapi.bale.ai")

# ── Emoji alphabet (256 unique single-codepoint emoji) ─────────────
# 1 byte ↔ 1 emoji. Built from four contiguous Unicode ranges that are
# fully assigned to single-codepoint emoji (no modifiers, no sequences).
ALPHABET = "".join(chr(cp) for cp in (
    list(range(0x1F600, 0x1F650))    # 80  emoticons (faces)
    + list(range(0x1F300, 0x1F321))  # 33  weather & sky
    + list(range(0x1F330, 0x1F380))  # 80  food & plants
    + list(range(0x1F400, 0x1F43F))  # 63  animals
))

# ── Tunnel tuning ────────────────────────────────────────────────────
# Max raw bytes per Bale message. With the 1-byte-per-emoji codec, the
# encoded payload is CHUNK_SIZE chars; plus a ~22-char header must fit
# in Bale's 4096-char message limit.
CHUNK_SIZE = _env_int("CHUNK_SIZE", 3500)

# SOCKS5 proxy listen address. On Railway (or any container host) set
# SOCKS_HOST=0.0.0.0 via env var so the proxy is reachable from outside
# the container; locally, 127.0.0.1 is safer (proxy stays on your machine).
SOCKS_HOST = os.environ.get("SOCKS_HOST", "127.0.0.1")
SOCKS_PORT = _env_int("SOCKS_PORT", 1080)

# Long-poll timeout for getUpdates (seconds)
POLL_TIMEOUT = _env_int("POLL_TIMEOUT", 30)

# Seconds to wait between send retries on transient errors
RETRY_DELAY = float(os.environ.get("RETRY_DELAY", "1.0"))
MAX_RETRIES = _env_int("MAX_RETRIES", 5)
