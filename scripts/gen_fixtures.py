#!/usr/bin/env python3
"""Append-only generator for `fixtures/guard_fixtures.json`.

Replaces the F7 draft generator, which could never match the canonical
contract: it emitted `{id, description, tx, state, expected}` cases with
`balance_cents` / `credit_ceiling_cents` state keys and letter-based token
fields (`"abcd"`) that crash `int(first44) % 97`.

This generator:

* loads the canonical file and NEVER rewrites or reorders existing cases,
* emits only canonical-schema cases (`{name, tx, state, expected}`) whose
  state keys are exactly what `guard.screen()` and `TxGuard.screen()` read,
* derives tokens from numeric 4-digit fields with the frozen mod-97 builder
  (4 time + 4 sender + 4 receiver + 8 amount + 4 seq + 20 nonce = 44, +4),
* appends only cases whose names are not already present (idempotent),
* refuses to touch the file when a generated name collides with different
  content.

Usage:
    python scripts/gen_fixtures.py            # append new cases (if any)
    python scripts/gen_fixtures.py --check    # exit 1 if there is anything to add
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "guard_fixtures.json"

BASE_TS = 1_620_000_000_000  # fixed so cases are deterministic


def build_token48(
    time4: str,
    sender4: str,
    receiver4: str,
    amount8: str,
    seq4: str,
    nonce20: str,
) -> str:
    """The frozen receipt-token builder: 44-digit payload + int(payload) % 97."""
    payload = f"{time4}{sender4}{receiver4}{amount8}{seq4}{nonce20}"
    if len(payload) != 44 or not payload.isdigit():
        raise ValueError(f"payload must be 44 digits, got {payload!r}")
    checksum = int(payload) % 97
    return f"{payload}{checksum:04d}"


def tamper(token: str, position: int) -> str:
    digits = list(token)
    digits[position] = str((int(digits[position]) + 1) % 10)
    return "".join(digits)


def good_token(amount_cents: int = 1000) -> str:
    return build_token48(
        time4="0000",
        sender4="0001",
        receiver4="0002",
        amount8=f"{amount_cents:08d}",
        seq4="0001",
        nonce20="12345678901234567890",
    )


def bad_token(amount_cents: int = 1000) -> str:
    return tamper(good_token(amount_cents), 20)


def tx(**overrides: Any) -> dict:
    case: dict[str, Any] = {
        "sender_account_id": "sender",
        "receiver_account_id": "recv",
        "amount": 1000,
        "nonce": "gen-nonce",
        "token48": None,
        "timestamp_ms": BASE_TS,
    }
    case.update(overrides)
    return case


def state(**overrides: Any) -> dict:
    case: dict[str, Any] = {
        "account_id": "sender",
        "balance": 2000,
        "credit_ceiling": 5000,
        "seq": 1,
        "recent_timestamps_ms": [],
        "seen_nonces": [],
        "blacklist": [],
    }
    case.update(overrides)
    return case


def deny(code: str, reason: str, score: int) -> dict:
    return {"decision": "DENY", "code": code, "reason": reason, "score": score}


ALLOW = {"decision": "ALLOW", "code": "OK", "reason": "", "score": 0}

RECENT = [BASE_TS - 1000, BASE_TS - 2000, BASE_TS - 3000, BASE_TS - 4000, BASE_TS - 5000]
JUST_OUTSIDE = [BASE_TS - 60_001, BASE_TS - 60_002, BASE_TS - 60_003, BASE_TS - 60_004, BASE_TS - 60_005]

EXTENDED: list[dict] = [
    {
        "name": "extended: zero balance still allows a zero amount",
        "tx": tx(amount=0),
        "state": state(balance=0),
        "expected": ALLOW,
    },
    {
        "name": "extended: zero ceiling blocks one cent",
        "tx": tx(amount=1),
        "state": state(credit_ceiling=0),
        "expected": deny("E_CEILING_EXCEEDED", "Exceeds credit ceiling", 100),
    },
    {
        "name": "extended: maximum transfer is allowed under the cap",
        "tx": tx(amount=10_000_000),
        "state": state(balance=10_000_000, credit_ceiling=10_000_000),
        "expected": ALLOW,
    },
    {
        "name": "extended: one cent over the maximum ceiling",
        "tx": tx(amount=10_000_001),
        "state": state(balance=10_000_001, credit_ceiling=10_000_000),
        "expected": deny("E_CEILING_EXCEEDED", "Exceeds credit ceiling", 100),
    },
    {
        "name": "extended: self payment beats a bad checksum",
        "tx": tx(receiver_account_id="sender", token48=bad_token()),
        "state": state(),
        "expected": deny("E_SELF_PAY", "Self payment", 10),
    },
    {
        "name": "extended: blacklist beats nonce replay",
        "tx": tx(nonce="seen-nonce"),
        "state": state(blacklist=["recv"], seen_nonces=["seen-nonce"]),
        "expected": deny("E_QUARANTINED_PEER", "Receiver blacklisted", 100),
    },
    {
        "name": "extended: nonce replay beats velocity",
        "tx": tx(nonce="seen-nonce"),
        "state": state(seen_nonces=["seen-nonce"], recent_timestamps_ms=RECENT),
        "expected": deny("E_DUPLICATE_TOKEN", "Duplicate nonce", 45),
    },
    {
        "name": "extended: velocity beats credit ceiling",
        "tx": tx(amount=6000),
        "state": state(recent_timestamps_ms=RECENT),
        "expected": deny("E_GUARDRAIL_BLOCKED", "velocity", 25),
    },
    {
        "name": "extended: six payments in the window trip velocity",
        "tx": tx(),
        "state": state(
            recent_timestamps_ms=RECENT + [BASE_TS - 600]
        ),
        "expected": deny("E_GUARDRAIL_BLOCKED", "velocity", 25),
    },
    {
        "name": "extended: five payments one ms outside the window are allowed",
        "tx": tx(),
        "state": state(recent_timestamps_ms=JUST_OUTSIDE),
        "expected": ALLOW,
    },
    {
        "name": "extended: valid token at exactly the balance limit",
        "tx": tx(amount=2000, token48=good_token(2000)),
        "state": state(balance=2000),
        "expected": ALLOW,
    },
    {
        "name": "extended: checksum failure wins over an over-ceiling amount",
        "tx": tx(amount=999_999, token48=bad_token(999_999)),
        "state": state(),
        "expected": deny("E_GUARDRAIL_BLOCKED", "checksum", 45),
    },
    {
        "name": "extended: an unknown receiver is not a pure-screen rule",
        "tx": tx(receiver_account_id="never-seen"),
        "state": state(),
        "expected": ALLOW,
    },
    {
        "name": "extended: an empty blacklist changes nothing",
        "tx": tx(),
        "state": state(blacklist=[]),
        "expected": ALLOW,
    },
    {
        "name": "extended: blacklist matches the exact receiver id only",
        "tx": tx(receiver_account_id="recv-2"),
        "state": state(blacklist=["recv"]),
        "expected": ALLOW,
    },
    {
        "name": "extended: a valid all-zero token verifies",
        "tx": tx(token48="0" * 48),
        "state": state(),
        "expected": ALLOW,
    },
]


def load_existing() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if there is anything to add")
    args = parser.parse_args()

    existing = load_existing()
    names = {case["name"] for case in existing}

    collisions = [
        case
        for case in EXTENDED
        if case["name"] in names
        and any(
            existing_case["expected"] != case["expected"]
            for existing_case in existing
            if existing_case["name"] == case["name"]
        )
    ]
    if collisions:
        print(f"REFUSING to write: {len(collisions)} generated case(s) collide with "
              f"different canonical content: {[c['name'] for c in collisions]}")
        return 2

    missing = [case for case in EXTENDED if case["name"] not in names]

    if args.check:
        if missing:
            print(f"{len(missing)} case(s) missing: {[c['name'] for c in missing]}")
            return 1
        print("fixtures are up to date")
        return 0

    if not missing:
        print(f"nothing to add; fixture file already contains all {len(EXTENDED)} extended cases")
        return 0

    updated = existing + missing
    FIXTURES.write_text(
        json.dumps(updated, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"appended {len(missing)} case(s); total now {len(updated)}")
    for case in missing:
        print(f"  + {case['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
