"""Cube wallet helpers — derive account keys; secrets are not written to disk."""

from __future__ import annotations

import json
import os
import re
from typing import Any

ACCOUNT_RE = re.compile(r"^[0-9a-fA-F]{64}$")
NSEC_RE = re.compile(r"nsec1[a-z0-9]+", re.I)
HEX64_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values: list[int]) -> int:
    generators = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            if (top >> i) & 1:
                chk ^= generators[i]
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convertbits(data: list[int], frombits: int, tobits: int, pad: bool) -> list[int] | None:
    acc, bits, ret = 0, 0, []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def _bech32_decode(addr: str) -> tuple[str, list[int]] | None:
    if any(ord(x) < 33 or ord(x) > 126 for x in addr):
        return None
    if addr.lower() != addr:
        return None
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr) or len(addr) > 90:
        return None
    hrp = addr[:pos]
    data = [CHARSET.find(c) for c in addr[pos + 1 :]]
    if -1 in data:
        return None
    if _polymod(_hrp_expand(hrp) + data) != 1:
        return None
    return hrp, data[:-6]


def _bech32_encode(hrp: str, data: list[int]) -> str:
    combined = _hrp_expand(hrp) + data
    checksum = [( _polymod(combined + [0] * 6) ^ 1) >> 5 * (5 - i) & 31 for i in range(6)]
    return hrp + "1" + "".join(CHARSET[d] for d in data + checksum)


def _decode_nsec(nsec: str) -> bytes:
    decoded = _bech32_decode(nsec.strip().lower())
    if not decoded or decoded[0] != "nsec":
        raise ValueError("invalid nsec")
    converted = _convertbits(decoded[1], 5, 8, False)
    if not converted or len(converted) != 32:
        raise ValueError("nsec must decode to 32 bytes")
    return bytes(converted)


def _encode_nsec(secret: bytes) -> str:
    if len(secret) != 32:
        raise ValueError("secret must be 32 bytes")
    data = _convertbits(list(secret), 8, 5, True)
    if data is None:
        raise ValueError("nsec encode failed")
    return _bech32_encode("nsec", data)


def _secret_to_account_hex(secret: bytes) -> str:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    key = ec.derive_private_key(
        int.from_bytes(secret, "big"), ec.SECP256K1(), default_backend()
    )
    pub = key.public_key().public_bytes(
        Encoding.X962, PublicFormat.CompressedPoint
    )
    if len(pub) != 33:
        raise ValueError("unexpected pubkey length")
    return pub[1:33].hex()


def generate_identity() -> dict[str, Any]:
    secret = os.urandom(32)
    nsec = _encode_nsec(secret)
    account = _secret_to_account_hex(secret)
    return {
        "ok": True,
        "nsec": nsec,
        "account": account,
        "note": (
            "Copy both now. TheBox does not store your nsec on the server. "
            "Your Cube account is the 64-char hex (x-only secp pubkey, Cube Signet)."
        ),
    }


def resolve_paste(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {"ok": False, "error": "Paste your Cube account hex or nsec."}

    match = NSEC_RE.search(text)
    if match or text.lower().startswith("nsec"):
        nsec = match.group(0) if match else text.strip()
        try:
            secret = _decode_nsec(nsec)
            account = _secret_to_account_hex(secret)
            return {"ok": True, "account": account, "source": "nsec"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    for candidate in HEX64_RE.findall(text.replace("0x", "").replace("0X", "")):
        h = candidate.lower()
        if ACCOUNT_RE.match(h):
            return {"ok": True, "account": h, "source": "hex"}

    try:
        blob = json.loads(text)
        for key in ("account", "account_key", "account_key_hex", "self_account_key"):
            val = blob.get(key)
            if isinstance(val, str):
                h = val.lower().replace("0x", "")
                if ACCOUNT_RE.match(h):
                    return {"ok": True, "account": h, "source": "json"}
        ak = blob.get("account_key")
        if isinstance(ak, list) and len(ak) == 32:
            h = bytes(int(x) & 0xFF for x in ak).hex()
            if ACCOUNT_RE.match(h):
                return {"ok": True, "account": h, "source": "json"}
    except json.JSONDecodeError:
        pass

    compact = re.sub(r"\s+", "", text).replace("0x", "").lower()
    if ACCOUNT_RE.match(compact):
        return {"ok": True, "account": compact, "source": "hex"}

    return {
        "ok": False,
        "error": (
            "Could not parse a Cube account. Paste 64-char hex, nsec1…, "
            "or JSON from `rootaccount` on your Cube node."
        ),
    }
