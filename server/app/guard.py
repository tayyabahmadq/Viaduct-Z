"""Payment guard rails.

Two entry points that must agree:

* `screen(tx, state)` — pure function, the contract pinned by
  `fixtures/guard_fixtures.json`. The Android `TxGuard.screen()` mirror must
  return the identical decision object for every fixture.
* `db_guard(db, sender, receiver, amount_cents, nonce)` — the authoritative,
  server-side version used by the API. It can only do what the database knows
  (it has no client-side velocity history), so the pure `screen()` is advisory
  client-side defence and `db_guard` is the enforcement point.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Device, Payment, utcnow

VELOCITY_WINDOW_MS = 60_000
VELOCITY_LIMIT = 5


def _deny(code: str, reason: str, score: int) -> Dict[str, Any]:
    return {"decision": "DENY", "code": code, "reason": reason, "score": score}


def _allow() -> Dict[str, Any]:
    return {"decision": "ALLOW", "code": "OK", "reason": "", "score": 0}


def screen(tx: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    sender = tx.get("sender_account_id")
    receiver = tx.get("receiver_account_id")
    amount = tx.get("amount")
    token48 = tx.get("token48")

    # R0 — malformed input. A token, when supplied, must be 48 numeric digits.
    if (
        sender is None
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or amount < 0
        or (
            token48 is not None
            and (len(token48) != 48 or not str(token48).isdigit())
        )
    ):
        return _deny("E_MALFORMED", "Malformed input", 100)

    # R1 — self payment.
    if receiver == sender:
        return _deny("E_SELF_PAY", "Self payment", 10)

    # R2 — quarantined / blacklisted recipient.
    if receiver in state.get("blacklist", ()):  # type: ignore[operator]
        return _deny("E_QUARANTINED_PEER", "Receiver blacklisted", 100)

    # R3 — receipt-token checksum.
    if token48 is not None:
        payload, received = token48[:44], token48[44:]
        if f"{int(payload) % 97:04d}" != received:
            return _deny("E_GUARDRAIL_BLOCKED", "checksum", 45)

    # R4 — nonce replay.
    if tx.get("nonce") in state.get("seen_nonces", ()):  # type: ignore[operator]
        return _deny("E_DUPLICATE_TOKEN", "Duplicate nonce", 45)

    # R5 — velocity: 5 or more payments inside the last 60 s.
    timestamp_ms = tx.get("timestamp_ms")
    if timestamp_ms is not None:
        threshold = timestamp_ms - VELOCITY_WINDOW_MS
        recent = [
            ts for ts in state.get("recent_timestamps_ms", ()) if ts >= threshold
        ]
        if len(recent) >= VELOCITY_LIMIT:
            return _deny("E_GUARDRAIL_BLOCKED", "velocity", 25)

    # R6 — per-transfer credit ceiling.
    if amount > int(state.get("credit_ceiling", 0)):
        return _deny("E_CEILING_EXCEEDED", "Exceeds credit ceiling", 100)

    # R7 — available balance.
    if amount > int(state.get("balance", 0)):
        return _deny("E_INSUFFICIENT_BALANCE", "Insufficient balance", 45)

    return _allow()


def db_guard(
    db: Session,
    sender: Device,
    receiver: Optional[Device],
    amount_cents: int,
    nonce: str,
) -> Tuple[bool, str]:
    if receiver is None:
        return False, "E_UNKNOWN_PEER"
    if sender.id == receiver.id:
        return False, "E_SELF_PAY"
    if amount_cents <= 0:
        return False, "E_MALFORMED"
    if amount_cents > sender.credit_ceiling_cents:
        return False, "E_CEILING_EXCEEDED"
    if amount_cents > sender.balance_cents:
        return False, "E_INSUFFICIENT_BALANCE"
    if db.scalar(select(Payment.id).where(Payment.nonce == nonce)) is not None:
        return False, "E_DUPLICATE_TOKEN"

    since = utcnow() - timedelta(minutes=1)
    recent = db.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.sender_id == sender.id, Payment.created_at >= since)
    )
    if (recent or 0) >= get_settings().rate_limit_per_minute:
        return False, "E_RATE_LIMIT"
    return True, "OK"
