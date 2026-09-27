"""
Bale Tunnel Node
================
A single node that simultaneously:
  - Listens on a local SOCKS5 port (acts as SOCKS5 server for local clients).
  - Opens real TCP connections on behalf of the peer (acts as forwarder for
    the peer's SOCKS5 clients).

Routing is done by conn_id:
  - conn_id in socks_queues  -> local SOCKS5 client initiated this conn;
                                 incoming msgs are responses for it.
  - conn_id in tcp_connections -> peer initiated this conn; we are doing the
                                  real TCP work for it.
  - unknown conn_id + CONNECT -> a new connection from the peer; open TCP.
"""

import asyncio
import logging
import signal
import struct
import time

import config
from bale_transport import BaleTransport
from tunnel_protocol import (
    Action,
    TunnelMessage,
    ReassemblyBuffer,
    chunk_data,
    new_conn_id,
    CONTROL_CONN_ID,
)


class TunnelConnection:
    """One TCP connection opened on behalf of the peer (forwarder side)."""

    def __init__(self, conn_id: str, transport: BaleTransport, tx_chat_id: int | str, log: logging.Logger):
        self.conn_id = conn_id
        self.transport = transport
        self.tx_chat_id = tx_chat_id
        self.log = log
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.reassembler = ReassemblyBuffer()
        self.seq = 0
        self._relay_task: asyncio.Task | None = None

    async def connect(self, host: str, port: int) -> bool:
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=15
            )
            self.log.info("[%s] connected to %s:%d", self.conn_id, host, port)
            self._relay_task = asyncio.create_task(self._relay_back())
            return True
        except Exception as exc:
            self.log.error("[%s] connect failed: %s", self.conn_id, exc)
            return False

    async def feed_data(self, msg: TunnelMessage):
        data = self.reassembler.feed(msg)
        if data and self.writer:
            try:
                self.writer.write(data)
                await self.writer.drain()
            except ConnectionError:
                await self.close()

    async def _relay_back(self):
        try:
            while self.reader:
                data = await self.reader.read(config.CHUNK_SIZE)
                if not data:
                    break
                msgs = chunk_data(self.conn_id, data, self.seq)
                for m in msgs:
                    await self.transport.send(self.tx_chat_id, m.encode_to_text())
                self.seq += len(msgs)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            close_msg = TunnelMessage(conn_id=self.conn_id, seq=0, action=Action.CLOSE)
            await self.transport.send(self.tx_chat_id, close_msg.encode_to_text())
            self.log.info("[%s] remote side closed", self.conn_id)

    async def close(self):
        if self._relay_task and not self._relay_task.done():
            self._relay_task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.writer = None
        self.reader = None


async def socks5_handshake(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> tuple[str, int] | None:
    """SOCKS5 negotiation. Returns (host, port) or None on failure."""
    header = await reader.readexactly(2)
    ver, nmethods = struct.unpack("!BB", header)
    if ver != 0x05:
        return None
    await reader.readexactly(nmethods)
    writer.write(b"\x05\x00")
    await writer.drain()

    req = await reader.readexactly(4)
    ver, cmd, _, atyp = struct.unpack("!BBBB", req)
    if ver != 0x05 or cmd != 0x01:
        writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
        await writer.drain()
        return None

    if atyp == 0x01:
        raw = await reader.readexactly(4)
        host = ".".join(str(b) for b in raw)
    elif atyp == 0x03:
        dlen = (await reader.readexactly(1))[0]
        host = (await reader.readexactly(dlen)).decode()
    elif atyp == 0x04:
        raw = await reader.readexactly(16)
        host = ":".join(f"{raw[i]:02x}{raw[i+1]:02x}" for i in range(0, 16, 2))
    else:
        return None

    port = struct.unpack("!H", await reader.readexactly(2))[0]
    writer.write(b"\x05\x00\x00\x01" + b"\x00\x00\x00\x00" + struct.pack("!H", 0))
    await writer.drain()
    return host, port


async def run_tunnel(
    name: str,
    bot_token: str,
    tx_chat_id: int | str,
    rx_chat_id: int | str,
    socks_host: str,
    socks_port: int,
    mode: str = "active",
):
    """Run a tunnel node: SOCKS5 server + TCP forwarder, sharing one bot.

    mode="active"  (iran_side): starts immediately, and broadcasts a HELLO
        on startup plus a keepalive HELLO every KEEPALIVE_INTERVAL seconds,
        and a BYE on clean shutdown, so the standby side knows when to
        wake up and when to go back to sleep.
    mode="standby" (foreign_side): stays idle — no SOCKS5 listener, no
        traffic relaying — until it receives a HELLO from the peer. Goes
        back to idle on a BYE, or automatically if no HELLO/keepalive is
        heard for IDLE_TIMEOUT seconds (covers a peer that crashed instead
        of shutting down cleanly).
    """
    assert mode in ("active", "standby")
    log = logging.getLogger(name)
    transport = BaleTransport(bot_token)

    # Connections we initiated as SOCKS5 server.
    # conn_id -> Queue of bytes-or-None (None signals EOF from peer)
    socks_queues: dict[str, asyncio.Queue[bytes | None]] = {}

    # Connections we terminate as TCP forwarder.
    tcp_connections: dict[str, TunnelConnection] = {}

    server: asyncio.base_events.Server | None = None
    last_peer_seen: float = 0.0

    async def start_session():
        nonlocal server
        if server is not None:
            return
        server = await asyncio.start_server(handle_socks_client, socks_host, socks_port)
        log.info("session ACTIVE — SOCKS5 proxy listening on %s:%d", socks_host, socks_port)

    async def stop_session(reason: str):
        nonlocal server
        if server is None:
            return
        s, server = server, None
        s.close()
        await s.wait_closed()
        for conn in list(tcp_connections.values()):
            await conn.close()
        tcp_connections.clear()
        for q in list(socks_queues.values()):
            await q.put(None)
        socks_queues.clear()
        log.info("session ENDED (%s) — back to standby, no traffic relayed", reason)

    async def poller():
        socks_reassemblers: dict[str, ReassemblyBuffer] = {}
        nonlocal last_peer_seen
        log.info("poller started (rx channel %s, mode=%s)", rx_chat_id, mode)
        while True:
            texts = await transport.poll(rx_chat_id)
            for text in texts:
                try:
                    msg = TunnelMessage.decode_from_text(text)
                except Exception:
                    continue
                cid = msg.conn_id

                # ── Control messages (HELLO / BYE) ──────────────────
                if cid == CONTROL_CONN_ID:
                    if msg.action == Action.HELLO:
                        last_peer_seen = time.monotonic()
                        if mode == "standby" and server is None:
                            log.info("HELLO received — waking up")
                            await start_session()
                    elif msg.action == Action.BYE:
                        if mode == "standby":
                            await stop_session("peer said BYE")
                    continue

                # In standby mode, ignore any real traffic until a HELLO
                # has actually started a session (defensive; shouldn't
                # normally happen since HELLO always precedes traffic).
                if mode == "standby" and server is None:
                    log.warning("[%s] dropped %s — no active session (peer hasn't said HELLO)", cid, msg.action)
                    continue

                # We are the SOCKS5 server side for this conn
                if cid in socks_queues:
                    if msg.action == Action.DATA:
                        rb = socks_reassemblers.setdefault(cid, ReassemblyBuffer())
                        data = rb.feed(msg)
                        if data:
                            await socks_queues[cid].put(data)
                    elif msg.action == Action.CLOSE:
                        await socks_queues[cid].put(None)
                        socks_reassemblers.pop(cid, None)
                    continue

                # We are the TCP forwarder side for this conn
                if cid in tcp_connections:
                    conn = tcp_connections[cid]
                    if msg.action == Action.DATA:
                        await conn.feed_data(msg)
                    elif msg.action == Action.CLOSE:
                        await conn.close()
                        tcp_connections.pop(cid, None)
                        log.info("[%s] connection torn down", cid)
                    continue

                # Unknown conn — only CONNECT is meaningful here
                if msg.action == Action.CONNECT:
                    try:
                        target = msg.payload.decode()
                        host, port_str = target.rsplit(":", 1)
                        port = int(port_str)
                    except Exception:
                        continue
                    conn = TunnelConnection(cid, transport, tx_chat_id, log)
                    ok = await conn.connect(host, port)
                    if ok:
                        tcp_connections[cid] = conn
                    else:
                        fail = TunnelMessage(conn_id=cid, seq=0, action=Action.CLOSE)
                        await transport.send(tx_chat_id, fail.encode_to_text())

    async def watchdog():
        """standby only: fall back to idle if the peer goes silent."""
        check_every = max(2, min(10, config.IDLE_TIMEOUT // 3))
        while True:
            await asyncio.sleep(check_every)
            if server is not None and (time.monotonic() - last_peer_seen) > config.IDLE_TIMEOUT:
                await stop_session(f"no HELLO for {config.IDLE_TIMEOUT}s")

    async def keepalive():
        """active only: announce presence so the peer wakes up / stays up."""
        hello = TunnelMessage(conn_id=CONTROL_CONN_ID, seq=0, action=Action.HELLO)
        while True:
            await transport.send(tx_chat_id, hello.encode_to_text())
            await asyncio.sleep(config.KEEPALIVE_INTERVAL)

    async def handle_socks_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        peer = writer.get_extra_info("peername")
        log.info("new SOCKS5 client from %s", peer)
        result = await socks5_handshake(reader, writer)
        if result is None:
            writer.close()
            return
        host, port = result
        log.info("CONNECT %s:%d", host, port)

        cid = new_conn_id()
        # seq counts DATA messages only; CONNECT/CLOSE carry seq=0 (ignored).
        seq = 0
        socks_queues[cid] = asyncio.Queue()

        connect_msg = TunnelMessage(
            conn_id=cid, seq=0, action=Action.CONNECT,
            payload=f"{host}:{port}".encode(),
        )
        await transport.send(tx_chat_id, connect_msg.encode_to_text())

        async def sender():
            nonlocal seq
            try:
                while True:
                    data = await reader.read(config.CHUNK_SIZE)
                    if not data:
                        break
                    msgs = chunk_data(cid, data, seq)
                    for m in msgs:
                        await transport.send(tx_chat_id, m.encode_to_text())
                    seq += len(msgs)
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                close_msg = TunnelMessage(conn_id=cid, seq=0, action=Action.CLOSE)
                await transport.send(tx_chat_id, close_msg.encode_to_text())

        async def receiver():
            try:
                while True:
                    data = await socks_queues[cid].get()
                    if data is None:
                        break
                    writer.write(data)
                    await writer.drain()
            except (ConnectionError, asyncio.CancelledError):
                pass

        s_task = asyncio.create_task(sender())
        r_task = asyncio.create_task(receiver())
        _, pending = await asyncio.wait(
            [s_task, r_task], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        socks_queues.pop(cid, None)
        writer.close()
        log.info("connection %s closed", cid)

    asyncio.create_task(poller())

    if mode == "active":
        await start_session()
        asyncio.create_task(keepalive())
    else:
        log.info("standing by on channel %s — waiting for peer HELLO before doing anything", rx_chat_id)
        asyncio.create_task(watchdog())

    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set_result, None)

    try:
        await stop
    finally:
        if mode == "active":
            bye = TunnelMessage(conn_id=CONTROL_CONN_ID, seq=0, action=Action.BYE)
            await transport.send(tx_chat_id, bye.encode_to_text())
        await stop_session("shutdown")
        await transport.close()
        log.info("shutdown complete")
