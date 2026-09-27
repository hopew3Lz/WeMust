# Bale Tunnel — Setup Guide

## Prerequisites
- Python 3.10+ on both servers
- A [Bale](https://bale.ai) account

## 1. Create Two Bale Bots

You need **two** bots — one for each side. (Bale's `getUpdates` does not
return a bot's own outgoing messages, so each side must poll a bot that
the *other* side sends through.)

1. Open Bale and search for **@BotFather**
2. Send `/newbot` and follow the prompts — this is the **Iran bot**
3. Copy its token (looks like `123456789:ABCDefgh...`)
4. Send `/newbot` again to create the **Foreign bot** and copy its token too

## 2. Create Two Channels

You need two channels — one for each direction of traffic:

1. **Upstream channel** (Iran → Foreign):
   - Create a new channel in Bale (e.g. "tunnel-up")
   - Add **both bots** as **admins** with permission to post messages
   - Get the channel's **chat ID** (see below)

2. **Downstream channel** (Foreign → Iran):
   - Create another channel (e.g. "tunnel-down")
   - Add **both bots** as **admins**
   - Get the channel's **chat ID**

### Getting the Chat ID

Option A — Send a message in the channel, then call:
```
curl "https://tapi.bale.ai/bot<YOUR_TOKEN>/getUpdates"
```
Look for `"chat": {"id": -100XXXXXXXXXX, ...}` in the response.

Option B — Use the channel username format: `"@my_channel_username"`

## 3. Configure

Edit `config.py` on **both** servers:

```python
IRAN_BOT_TOKEN    = "123456789:ABCDefgh..."    # the Iran bot
FOREIGN_BOT_TOKEN = "987654321:ZYXWvuts..."    # the Foreign bot
UPSTREAM_CHAT_ID  = -1001234567890             # or "@tunnel_up"
DOWNSTREAM_CHAT_ID = -1001234567891            # or "@tunnel_down"
```

## 4. Install Dependencies

On both servers:
```bash
pip install -r requirements.txt
```

## 5. Run

**Foreign server** (start first):
```bash
python foreign_side.py
```

**Iran server**:
```bash
python iran_side.py
```

## 6. Use

The tunnel works in BOTH directions. Each side runs a SOCKS5 server on
`127.0.0.1:1080` of its own machine:

- **From inside Iran** → outbound: point your browser at the Iran
  server's `127.0.0.1:1080` to reach the open internet via the foreign
  forwarder.
- **From outside Iran** → into Iran: point your browser at the foreign
  server's `127.0.0.1:1080` to reach Iranian-only services via the iran
  forwarder.

All traffic flows through Bale as emoji-encoded messages.

## Architecture

```
                ── forward (iran → internet) ──────▶
[Browser]──SOCKS5──[iran_side]──emoji──[upstream  channel]──emoji──[foreign_side]──TCP──[Internet]
                                       [downstream channel]
                ◀─────────  reverse (foreign → iran) ──
[Browser]──SOCKS5──[foreign_side]──emoji──[downstream channel]──emoji──[iran_side]──TCP──[Iranian host]
                                          [upstream   channel]
```

Both channels carry traffic in both directions. Routing inside each node
is done by `conn_id`: connections initiated locally vs. initiated by the
peer are tracked in separate tables.

## Troubleshooting

- **"Alphabet must contain exactly 32 characters"** — the emoji alphabet in `config.py` must have exactly 32 single-codepoint emoji
- **Messages not arriving** — make sure **both** bots are admins in **both** channels (a bot does not receive its own posts back via getUpdates, so each side must poll the other side's bot)
- **Slow performance** — this tunnel is limited by Bale's message rate; it works for browsing but not for large downloads
- **Connection refused on 1080** — make sure `iran_side.py` is running and `SOCKS_HOST`/`SOCKS_PORT` are correct
