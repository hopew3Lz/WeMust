# Deploying the Foreign Side on Railway

Only `foreign_side.py` belongs on Railway. It needs outbound access to
`tapi.bale.ai` and the open internet, and does **not** need a public
inbound port for the standard (Iran → internet) use case, so Railway's
free trial resources are enough for light testing.

`iran_side.py` must run somewhere inside Iran (or wherever the client's
browser can reach `127.0.0.1:1080` — your own machine or a server you
have local/VPN access to). Railway is outside Iran, so it can never host
the Iran side for the normal use case.

## Steps

1. **Create bots and channels first.** Follow [SETUP.md](SETUP.md) to
   get `IRAN_BOT_TOKEN`, `FOREIGN_BOT_TOKEN`, `UPSTREAM_CHAT_ID`,
   `DOWNSTREAM_CHAT_ID`. Do this before deploying — Railway needs real
   values, not placeholders. Register the bots with a number that is
   **not** your personal phone number (see the security warning in
   [README.md](README.md)).

2. **New Railway project** → "Deploy from GitHub repo" (push this
   folder to a repo first) or "Empty Project" + drag-and-drop / Railway
   CLI (`railway up`) if you don't want a public repo.

3. Railway auto-detects the `Dockerfile`. `railway.json` in this repo
   already sets the start command to `python -u foreign_side.py`, so no
   manual override needed. If Railway ignores it, set it by hand:
   **Settings → Deploy → Custom Start Command** → `python -u foreign_side.py`.

4. **Set environment variables** (Settings → Variables), one at a time
   or via "Raw Editor" pasting your filled-in `.env` (see
   `.env.example`):
   ```
   IRAN_BOT_TOKEN=...
   FOREIGN_BOT_TOKEN=...
   UPSTREAM_CHAT_ID=...
   DOWNSTREAM_CHAT_ID=...
   ```
   Leave `SOCKS_HOST` unset (defaults to `127.0.0.1`) — the foreign
   side's own SOCKS5 port is only used for the reverse direction
   (foreign → Iran). No need to expose it publicly unless you actually
   use that direction.

5. **Deploy.** Check the Railway logs — you should see
   `poller started (rx channel ...)` and `SOCKS5 proxy listening on
   127.0.0.1:1080`.

6. On the Iran side, run `iran_side.py` (locally, in Docker, or on a
   server you control) with the same four env vars, and point your
   browser's SOCKS5 proxy at that machine's `127.0.0.1:1080`.

## Cost note

Railway no longer has a permanent free tier: new accounts get a 30-day
trial with $5 of credit, then you're moved to a paid plan (Hobby, from
$5/month) or a limited $1/month free plan if eligible. A single
low-traffic Python process easily fits inside the trial credit for
testing purposes, but check Railway's current pricing page before
relying on it long-term.
