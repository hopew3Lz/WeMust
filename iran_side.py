"""
Iran-side Tunnel Node
=====================
Run on the server inside Iran.

It does two things simultaneously:
  - Listens on a local SOCKS5 port: traffic from local apps is tunnelled
    OUT through the foreign side (the original use case).
  - Acts as a TCP forwarder for SOCKS5 clients on the FOREIGN side: when a
    user outside Iran wants to reach an Iranian host, this node opens the
    real TCP connection here.

Usage:
    python iran_side.py
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
        name="iran",
        bot_token=config.IRAN_BOT_TOKEN,
        tx_chat_id=config.UPSTREAM_CHAT_ID,   # iran transmits here
        rx_chat_id=config.DOWNSTREAM_CHAT_ID, # iran receives from here
        socks_host=config.SOCKS_HOST,
        socks_port=config.SOCKS_PORT,
    ))
