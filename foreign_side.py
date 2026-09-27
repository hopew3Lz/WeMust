"""
Foreign-side Tunnel Node
========================
Run on the server outside Iran.

It does two things simultaneously:
  - Acts as a TCP forwarder for SOCKS5 clients on the IRAN side: opens real
    TCP connections to the open internet (the original use case).
  - Listens on a local SOCKS5 port: traffic from local apps is tunnelled
    INTO Iran (so foreign users can reach Iranian-only services).

STANDBY MODE: this node starts idle — it does NOT open its SOCKS5 port
and does NOT relay any traffic until it receives a HELLO from iran_side.py.
It goes back to idle automatically on a clean BYE from iran_side, or after
config.IDLE_TIMEOUT seconds of silence (e.g. if iran_side crashed). This
keeps the Bale channels quiet and avoids doing any relay work while
iran_side.py isn't actually running.

Usage:
    python foreign_side.py
"""

import asyncio
import logging

import config
from bale_tunnel import run_tunnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


if __name__ == "__main__":
    asyncio.run(run_tunnel(
        name="foreign",
        bot_token=config.FOREIGN_BOT_TOKEN,
        tx_chat_id=config.DOWNSTREAM_CHAT_ID, # foreign transmits here
        rx_chat_id=config.UPSTREAM_CHAT_ID,   # foreign receives from here
        socks_host=config.SOCKS_HOST,
        socks_port=config.SOCKS_PORT,
        mode="standby",
    ))
