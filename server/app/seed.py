"""Demo seed — six wallets so a fresh deployment has peers to pay."""

from __future__ import annotations

import secrets

from sqlalchemy import select

from .db import SessionLocal
from .models import Device, new_id, utcnow
from .tokens import build_token48, make_nonce

DEMO_ACCOUNTS = [
    ("Aarav Shah", 250_000),
    ("Mei Chen", 180_000),
    ("Lucas Meyer", 92_000),
    ("Sofia Rossi", 410_000),
    ("Noah Kim", 75_000),
    ("Aisha Khan", 320_000),
]


def seed_if_empty() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Device.id).limit(1)) is not None:
            return

        for index, (name, balance) in enumerate(DEMO_ACCOUNTS, start=1):
            short = f"{index:04d}"
            db.add(
                Device(
                    id=new_id(),
                    name=name,
                    short_hash=short,
                    token48=build_token48(short, "0000", 0, 0, make_nonce()),
                    api_token=secrets.token_urlsafe(32),
                    balance_cents=balance,
                    credit_ceiling_cents=500_000,
                    seq=0,
                    created_at=utcnow(),
                    last_seen_at=utcnow(),
                )
            )
        db.commit()
