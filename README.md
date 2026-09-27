# Bale Tunnel — SOCKS5 Proxy over Bale Messenger

> A working **proxy over Bale** (پروکسی روی بله): tunnel ordinary internet
> traffic through the [Bale messenger](https://bale.ai) Bot API by encoding
> TCP packets as emoji inside channel messages.

**Keywords:** bale proxy, proxy over bale, bale tunnel, socks5 proxy, bale
messenger proxy, tunnel traffic through bale, bale bot api proxy, پروکسی بله.

---

## What is Bale Tunnel?

Bale Tunnel turns the Bale messenger into a transport layer for a normal
**SOCKS5 proxy**. Instead of speaking directly to a remote server, your
TCP traffic is:

1. Accepted by a local SOCKS5 server on `127.0.0.1:1080`.
2. Sliced into chunks and **encoded as emoji** (1 byte ↔ 1 emoji).
3. Posted as plain text messages into a Bale channel via the Bot API.
4. Read back on the other side, decoded, and replayed onto a real TCP socket.

Because the only thing crossing the network is regular Bale Bot API
traffic (`tapi.bale.ai`), the tunnel rides on infrastructure that is
normally reachable even when other routes are not.

The tunnel is **bidirectional**: each side runs both a SOCKS5 server and a
TCP forwarder, so it can carry traffic out *and* in.

## How It Works

```
                ── forward (iran → internet) ──────▶
[Browser]──SOCKS5──[iran_side]──emoji──[upstream  channel]──emoji──[foreign_side]──TCP──[Internet]
                                       [downstream channel]
                ◀─────────  reverse (foreign → iran) ──
[Browser]──SOCKS5──[foreign_side]──emoji──[downstream channel]──emoji──[iran_side]──TCP──[Iranian host]
                                          [upstream   channel]
```

- **`emoji_codec.py`** — direct 1-byte-per-emoji lookup table (256 unique
  single-codepoint emoji).
- **`tunnel_protocol.py`** — message framing, chunking, and in-order
  reassembly (`CONNECT` / `DATA` / `CLOSE`).
- **`bale_transport.py`** — thin async wrapper over the Bale Bot API
  (`sendMessage` + `getUpdates`), with retry and rate-limit handling.
- **`bale_tunnel.py`** — the node: SOCKS5 server + TCP forwarder, routed
  by `conn_id`.
- **`iran_side.py` / `foreign_side.py`** — the two entry points.

## ⚠️ Security Warning — Do Not Use Your Personal Phone Number

**Never register the Bale account or bots used by this tunnel with your
own / personal phone number.**

- Bale requires a phone number to create an account, and that number is
  directly tied to a real identity.
- Every message this tunnel sends is attributable to the bot's owner
  account. Using your personal number links *all* tunnelled traffic back
  to you.
- Use a separate, dedicated number that is not connected to your identity,
  banking, or primary accounts.

Treat this project as **experimental software for research and
educational purposes**. You are responsible for understanding the legal
and personal risks in your jurisdiction before running it. The tunnel
content is obfuscated (emoji-encoded) but **not** strongly encrypted —
do not rely on it for anonymity or to protect sensitive data.

## Features

- Standard **SOCKS5** interface — works with any browser or app.
- **Bidirectional** tunnelling (outbound and inbound).
- No servers to expose: traffic flows only through the Bale Bot API.
- Pure Python, single dependency (`aiohttp`), fully `asyncio`-based.
- Automatic chunking, reassembly, retries, and rate-limit back-off.

## Requirements

- Python 3.10+ **or** Docker (see [Run with Docker](#run-with-docker))
- Two servers (one on each side of the link)
- Two Bale bots and two Bale channels (see [SETUP.md](SETUP.md))

## Installation

```bash
git clone <your-repo-url>
cd sosers
pip install -r requirements.txt
```

## Configuration

Copy your bot tokens and channel IDs into [config.py](config.py):

```python
IRAN_BOT_TOKEN     = "..."   # token of the Iran-side bot
FOREIGN_BOT_TOKEN  = "..."   # token of the Foreign-side bot
UPSTREAM_CHAT_ID   = ...     # Iran → Foreign channel
DOWNSTREAM_CHAT_ID = ...     # Foreign → Iran channel
```

**Do not commit real tokens.** Keep `config.py` filled with placeholders
in version control and add your real values only on the machines that run
the tunnel.

## Usage

Start the foreign side first, then the Iran side:

```bash
# on the server outside Iran
python foreign_side.py

# on the server inside Iran
python iran_side.py
```

Then point your browser/app at the SOCKS5 proxy:

- **Host:** `127.0.0.1`
- **Port:** `1080`

Full step-by-step instructions (creating bots, channels, getting chat
IDs) are in **[SETUP.md](SETUP.md)**.

## Run with Docker

The repository ships a [Dockerfile](Dockerfile) and
[docker-compose.yml](docker-compose.yml) so you can run either side
without installing Python locally.

### 1. Configure

Edit [config.py](config.py) as usual with your bot tokens and channel
IDs. **One extra step for containers:** bind the SOCKS5 server to all
interfaces, otherwise the published port is unreachable from the host:

```python
SOCKS_HOST = "0.0.0.0"
```

The container still only publishes that port back to the host's
`127.0.0.1:1080`, so it is not exposed to your wider network.

### 2. Run with Docker Compose (recommended)

Start only the side you need on each server:

```bash
# on the server outside Iran
docker compose up -d --build foreign

# on the server inside Iran
docker compose up -d --build iran
```

`config.py` is bind-mounted, so you can change tokens and just
`docker compose restart` — no rebuild required. Follow logs with
`docker compose logs -f`.

### 3. Or run with plain Docker

```bash
docker build -t bale-tunnel .

# foreign side
docker run -d --name bale-foreign \
  -v "$(pwd)/config.py:/app/config.py:ro" \
  -p 127.0.0.1:1080:1080 \
  bale-tunnel foreign_side.py

# iran side
docker run -d --name bale-iran \
  -v "$(pwd)/config.py:/app/config.py:ro" \
  -p 127.0.0.1:1080:1080 \
  bale-tunnel iran_side.py
```

The image runs as a non-root user and selects the side from the command
argument (`iran_side.py` or `foreign_side.py`).

## Performance & Limitations

- **This is not a high-speed VPN.** Throughput is capped by Bale's
  message rate limits. It is fine for light browsing, messaging, and
  text-heavy sites; it is **not** suitable for streaming or large
  downloads.
- Latency is higher than a direct connection because every packet makes a
  round trip through the Bale API and a long-poll cycle.
- The emoji codec roughly **doubles** the byte size on the wire.
- The transport is obfuscation, not encryption. Always use HTTPS/TLS on
  top of it for any real privacy.

## FAQ

**Is this a VPN?**
No. It is a SOCKS5 proxy whose transport happens to be Bale messages.

**Can Bale see my traffic?**
The message *content* is emoji-encoded, not encrypted. Assume anything
that passes through the Bale API can be observed. Use TLS end-to-end.

**Why two bots and two channels?**
Bale's `getUpdates` does not return a bot's own outgoing messages, so
each side must poll a bot that the *other* side sends through.

**It is slow / messages don't arrive — help?**
See the Troubleshooting section in [SETUP.md](SETUP.md).

## Disclaimer

This software is provided **as-is, for educational and research purposes
only**. The authors do not endorse and are not responsible for any misuse.
You are solely responsible for complying with the laws and terms of
service that apply to you, including those of Bale messenger. Running a
proxy may violate local regulations or Bale's terms — understand the
risks before you use it.

## License

MIT — see [LICENSE](LICENSE) if present, otherwise treat as MIT.
