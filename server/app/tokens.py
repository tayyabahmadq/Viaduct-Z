"""The 48-digit receipt token.

Layout (48 digits, all numeric):

    time     4   minutes since EPOCH, mod 10000
    sender   4   sender short hash
    receiver 4   receiver short hash
    amount   8   amount in cents
    seq      4   sender's monotonic sequence number, mod 10000
    nonce   20   random, unique per payment
    ------------
    payload 44
    check    4   int(payload) % 97, zero padded

The token is a *receipt artefact*: it is derived from a settled payment and can
be verified offline. It is not a credential — `Device.api_token` is.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple, TypedDict

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

PAYLOAD_DIGITS = 44
TOKEN_DIGITS = 48
NONCE_DIGITS = 20


class TokenParts(TypedDict):
    minutes: int
    sender_short: str
    receiver_short: str
    amount_cents: int
    seq: int
    nonce: str
    checksum: str


def short_hash(seed: str) -> str:
    """Stable 4-digit id derived from a seed string."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16) % 10000:04d}"


def make_nonce() -> str:
    return f"{secrets.randbelow(10 ** NONCE_DIGITS):0{NONCE_DIGITS}d}"


def checksum(payload44: str) -> str:
    return f"{int(payload44) % 97:04d}"


def build_token48(
    sender_short: str,
    receiver_short: str,
    amount_cents: int,
    seq: int,
    nonce: str,
    ts: Optional[datetime] = None,
) -> str:
    ts = ts or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    minutes = int((ts - EPOCH).total_seconds() // 60) % 10000
    payload = (
        f"{minutes:04d}"
        + f"{int(sender_short):04d}"
        + f"{int(receiver_short):04d}"
        + f"{int(amount_cents):08d}"
        + f"{seq % 10000:04d}"
        + nonce.zfill(NONCE_DIGITS)
    )
    if len(payload) != PAYLOAD_DIGITS:
        raise ValueError(f"payload must be {PAYLOAD_DIGITS} digits, got {len(payload)}")
    return payload + checksum(payload)


def verify_token48(token: str) -> Tuple[bool, str]:
    if len(token) != TOKEN_DIGITS or not token.isdigit():
        return False, "E_MALFORMED"
    payload, received = token[:PAYLOAD_DIGITS], token[PAYLOAD_DIGITS:]
    if checksum(payload) != received:
        return False, "E_TOKEN_CHECKSUM"
    return True, "OK"


def decode_token48(token: str) -> Optional[TokenParts]:
    """Decode a *valid* token; returns None when the token is malformed or forged."""
    ok, _ = verify_token48(token)
    if not ok:
        return None
    return TokenParts(
        minutes=int(token[0:4]),
        sender_short=token[4:8],
        receiver_short=token[8:12],
        amount_cents=int(token[12:20]),
        seq=int(token[20:24]),
        nonce=token[24:44],
        checksum=token[44:48],
    )
