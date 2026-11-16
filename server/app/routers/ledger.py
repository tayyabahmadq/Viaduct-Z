"""Double-entry journal health: summary for the API, backfill for old rows."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_device
from ..models import Device, LedgerEntry, Payment
from ..schemas import LedgerSummaryOut

router = APIRouter(prefix="/api/v1/ledger", tags=["ledger"])


def summarize(db: Session) -> dict:
    debits = (
        db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
                LedgerEntry.direction == "DEBIT"
            )
        )
        or 0
    )
    credits = (
        db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
                LedgerEntry.direction == "CREDIT"
            )
        )
        or 0
    )
    settled = (
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
                Payment.status == "COMPLETED"
            )
        )
        or 0
    )
    completed = (
        db.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.status == "COMPLETED")
        )
        or 0
    )
    entries = db.scalar(select(func.count()).select_from(LedgerEntry)) or 0

    paired_ids = (
        select(LedgerEntry.payment_id)
        .group_by(LedgerEntry.payment_id)
        .having(func.count() == 2)
        .subquery()
    )
    paired = db.scalar(select(func.count()).select_from(paired_ids)) or 0
    missing = max(completed - paired, 0)

    return {
        "total_debits": debits,
        "total_credits": credits,
        "settled_cents": settled,
        "completed_payments": completed,
        "journal_entries": entries,
        "missing_entries": missing,
        "balanced": (
            debits == credits == settled
            and entries == completed * 2
            and missing == 0
        ),
    }


@router.get("/summary", response_model=LedgerSummaryOut)
def ledger_summary(
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
) -> LedgerSummaryOut:
    """Journal totals for the demo. Requires auth; exposes no per-user data."""
    return LedgerSummaryOut(**summarize(db))
