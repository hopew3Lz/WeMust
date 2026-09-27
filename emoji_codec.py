"""
Emoji Byte Codec
================
1 byte ↔ 1 emoji. Each of 256 byte values maps to a unique single-codepoint
character. No base conversion — just a direct lookup table.
"""


class EmojiCodec:
    def __init__(self, alphabet: str):
        chars = list(alphabet)
        if len(chars) != 256:
            raise ValueError(
                f"Alphabet must contain exactly 256 characters, got {len(chars)}"
            )
        if len(set(chars)) != 256:
            raise ValueError("Alphabet characters must all be unique")
        self.alphabet = chars
        self.lookup = {ch: i for i, ch in enumerate(chars)}

    def encode(self, data: bytes) -> str:
        return "".join(self.alphabet[b] for b in data)

    def decode(self, text: str) -> bytes:
        try:
            return bytes(self.lookup[ch] for ch in text)
        except KeyError as exc:
            raise ValueError(f"Character {exc.args[0]!r} not in alphabet") from exc
