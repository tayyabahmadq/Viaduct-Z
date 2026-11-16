"""One-shot backfill of missing journal entries.

Older demo databases (and any payment written before the journal existed) have
COMPLETED payments with no `ledger_entries`. The API still works; the ledger
summary reports `missing_entries > 0` until this runs.

    python -m app.backfill
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import LedgerEntry, Payment


def backfill_ledger(db: Session) -> int:
    """Repair COMPLETED payments that are missing one or both journal rows."""
    payments = db.scalars(
        select(Payment).where(Payment.status == "COMPLETED")
    ).all()

    repaired = 0
    for payment in payments:
        existing = set(
            db.scalars(
                select(LedgerEntry.direction).where(
                    LedgerEntry.payment_id == payment.id
                )
            ).all()
        )
        if {"DEBIT", "CREDIT"} <= existing:
            continue

        if "DEBIT" not in existing:
            db.add(
                LedgerEntry(
                    payment_id=payment.id,
                    device_id=payment.sender_id,
                    direction="DEBIT",
                    amount_cents=payment.amount_cents,
                )
            )
        if "CREDIT" not in existing:
            db.add(
                LedgerEntry(
                    payment_id=payment.id,
                    device_id=payment.receiver_id,
                    direction="CREDIT",
                    amount_cents=payment.amount_cents,
                )
            )
        repaired += 1

    db.commit()
    return repaired


if __name__ == "__main__":
    with SessionLocal() as session:
        count = backfill_ledger(session)
    print(f"backfilled {count} completed payment(s)")
