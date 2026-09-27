"""
Tunnel Protocol
===============
Handles message framing, chunking, and reassembly over Bale messages.

Wire format (plain text, fields separated by '|'):
    {conn_id}|{seq}|{action}|{base32_payload}

Actions:
    CONNECT  – open a new TCP connection (payload = host:port)
    DATA     – tunnel data chunk
    CLOSE    – tear down the connection
    HELLO    – control message: peer is active / keepalive
    BYE      – control message: peer is shutting down cleanly
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from emoji_codec import EmojiCodec
import config

codec = EmojiCodec(config.ALPHABET)

SEPARATOR = "|"

# conn_id used for control messages (HELLO/BYE) — never a real connection.
CONTROL_CONN_ID = "ctl"


class Action(str, Enum):
    CONNECT = "C"
    DATA = "D"
    CLOSE = "X"
    HELLO = "H"
    BYE = "B"


@dataclass
class TunnelMessage:
    conn_id: str
    seq: int
    action: Action
    payload: bytes = b""

    def encode_to_text(self) -> str:
        """Serialize to a single Bale-message string."""
        encoded = codec.encode(self.payload) if self.payload else ""
        return SEPARATOR.join(
            [self.conn_id, str(self.seq), self.action.value, encoded]
        )

    @classmethod
    def decode_from_text(cls, text: str) -> "TunnelMessage":
        """Parse a Bale-message string back into a TunnelMessage."""
        parts = text.split(SEPARATOR, 3)
        if len(parts) != 4:
            raise ValueError(f"bad message format: {text[:80]!r}")
        conn_id, seq_str, action_str, encoded = parts
        action = Action(action_str)
        payload = codec.decode(encoded) if encoded else b""
        return cls(conn_id=conn_id, seq=int(seq_str), action=action, payload=payload)


def new_conn_id() -> str:
    """Generate a short unique connection identifier."""
    return uuid.uuid4().hex[:8]


def chunk_data(conn_id: str, data: bytes, start_seq: int) -> list[TunnelMessage]:
    """Split *data* into CHUNK_SIZE pieces wrapped as DATA messages."""
    msgs: list[TunnelMessage] = []
    offset = 0
    seq = start_seq
    while offset < len(data):
        chunk = data[offset : offset + config.CHUNK_SIZE]
        msgs.append(TunnelMessage(conn_id=conn_id, seq=seq, action=Action.DATA, payload=chunk))
        offset += config.CHUNK_SIZE
        seq += 1
    return msgs


@dataclass
class ReassemblyBuffer:
    """Reorders and reassembles DATA messages for one connection."""

    expected_seq: int = 0
    buf: dict[int, bytes] = field(default_factory=dict)

    def feed(self, msg: TunnelMessage) -> bytes:
        """Add a message; return contiguous bytes available (may be empty)."""
        if msg.action != Action.DATA:
            return b""
        self.buf[msg.seq] = msg.payload
        out = bytearray()
        while self.expected_seq in self.buf:
            out.extend(self.buf.pop(self.expected_seq))
            self.expected_seq += 1
        return bytes(out)
