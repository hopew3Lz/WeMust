"""
Bale Transport Layer
====================
Thin async wrapper around the Bale Bot HTTP API.
Only uses sendMessage and getUpdates — no heavy framework needed.
"""

import asyncio
import logging

import aiohttp

import config

log = logging.getLogger(__name__)


class BaleTransport:
    """Send and receive text messages through a Bale channel."""

    def __init__(self, bot_token: str):
        self._api = f"{config.BALE_API_BASE}/bot{bot_token}"
        self._session: aiohttp.ClientSession | None = None
        self._offset: int = 0  # getUpdates offset (per-instance)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Send ─────────────────────────────────────────────────────────
    async def send(self, chat_id: int | str, text: str) -> dict | None:
        """Send a text message to *chat_id*.  Retries on transient errors."""
        session = await self._get_session()
        url = f"{self._api}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return data.get("result")
                    # Rate-limited — honour retry_after
                    retry_after = (
                        data.get("parameters", {}).get("retry_after")
                    )
                    if retry_after:
                        log.warning("rate-limited, waiting %ss", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    log.error("sendMessage failed: %s", data)
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                log.warning("send attempt %d failed: %s", attempt, exc)
                await asyncio.sleep(config.RETRY_DELAY * attempt)

        log.error("sendMessage gave up after %d attempts", config.MAX_RETRIES)
        return None

    # ── Receive ──────────────────────────────────────────────────────
    async def poll(self, allowed_chat_id: int | str) -> list[str]:
        """Long-poll for new text messages in *allowed_chat_id*.

        Returns a list of message texts (may be empty).
        Updates the internal offset so each message is seen only once.
        """
        session = await self._get_session()
        url = f"{self._api}/getUpdates"
        params = {
            "offset": self._offset,
            "limit": 100,
            "timeout": config.POLL_TIMEOUT,
        }

        try:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=config.POLL_TIMEOUT + 10)
            ) as resp:
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("getUpdates network error: %s", exc)
            return []

        if not data.get("ok"):
            log.warning("getUpdates not-ok response: %s", data)
            return []

        updates = data.get("result", [])
        if updates:
            log.info(
                "poll(want=%s, offset=%s) got %d update(s)",
                allowed_chat_id, self._offset, len(updates),
            )

        texts: list[str] = []
        for update in updates:
            update_id = update["update_id"]
            self._offset = max(self._offset, update_id + 1)

            # Inspect every update kind so we can see what Bale is sending us
            kinds = [k for k in update.keys() if k != "update_id"]
            msg = update.get("message") or update.get("channel_post")
            if not msg:
                log.info("  update %s: no message/channel_post (kinds=%s)", update_id, kinds)
                continue

            chat = msg.get("chat", {})
            cid = chat.get("id") or chat.get("username")
            chat_type = chat.get("type")
            text = msg.get("text", "")
            sender = (msg.get("from") or {}).get("id")

            log.info(
                "  update %s: kinds=%s chat_id=%s chat_type=%s from=%s text_len=%d",
                update_id, kinds, cid, chat_type, sender, len(text),
            )

            # Only accept messages from the channel we care about
            if str(cid) == str(allowed_chat_id) and text:
                texts.append(text)
            else:
                log.info(
                    "    -> filtered out (want chat_id=%s, got chat_id=%s, text_empty=%s)",
                    allowed_chat_id, cid, not bool(text),
                )

        return texts
