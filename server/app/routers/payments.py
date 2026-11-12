"""Payments: create, history, offline batch sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_device
from ..guard import db_guard
from ..models import Device, Payment, iso, new_id, utcnow
from ..schemas import (
    BatchItemResult,
    BatchRequest,
    BatchResponse,
    HistoryItem,
    PaymentRequest,
    Receipt,
)
from ..tokens import build_token48, make_nonce

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def _receipt(payment: Payment) -> Receipt:
    return Receipt(
        status=payment.status,  # type: ignore[arg-type]
        transaction_id=payment.id,
        amount_cents=payment.amount_cents,
        token48=payment.token48,
        sender_balance=payment.sender_balance_after,
        receiver_balance=payment.receiver_balance_after,
        reason_code=payment.reason_code,
    )


def _decline(
    sender: Device,
    body: PaymentRequest,
    nonce: str,
    reason: str,
    receiver_balance: int = 0,
) -> Payment:
    """A declined payment is still recorded — it is part of the audit trail."""
    return Payment(
        id=new_id(),
        sender_id=sender.id,
        receiver_id=None,
        receiver_token48=body.to_token48,
        amount_cents=body.amount_cents,
        memo=body.memo,
        idempotency_key=body.idempotency_key,
        nonce=nonce,
        token48=None,
        status="DECLINED",
        reason_code=reason,
        sender_balance_after=sender.balance_cents,
        receiver_balance_after=receiver_balance,
        created_at=utcnow(),
    )


def _apply(
    db: Session, sender: Device, body: PaymentRequest
) -> tuple[Payment, bool]:
    # Lock the sender row so concurrent payments cannot both spend the same cents.
    locked_sender = db.scalar(
        select(Device).where(Device.id == sender.id).with_for_update()
    )
    if locked_sender is not None:
        sender = locked_sender

    receiver = db.scalar(
        select(Device).where(Device.token48 == body.to_token48).with_for_update()
    )
    nonce = make_nonce()

    ok, reason = db_guard(db, sender, receiver, body.amount_cents, nonce)
    if not ok:
        return (
            _decline(
                sender,
                body,
                nonce,
                reason,
                receiver.balance_cents if receiver else 0,
            ),
            False,
        )

    assert receiver is not None
    sender.seq += 1
    sender.balance_cents -= body.amount_cents
    receiver.balance_cents += body.amount_cents

    payment = Payment(
        id=new_id(),
        sender_id=sender.id,
        receiver_id=receiver.id,
        receiver_token48=receiver.token48,
        amount_cents=body.amount_cents,
        memo=body.memo,
        idempotency_key=body.idempotency_key,
        nonce=nonce,
        token48=build_token48(
            sender.short_hash,
            receiver.short_hash,
            body.amount_cents,
            sender.seq,
            nonce,
        ),
        status="COMPLETED",
        reason_code=None,
        sender_balance_after=sender.balance_cents,
        receiver_balance_after=receiver.balance_cents,
        created_at=utcnow(),
    )
    return payment, True


@router.post("", response_model=Receipt)
def create_payment(
    body: PaymentRequest,
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
) -> Receipt:
    existing = db.scalar(
        select(Payment).where(Payment.idempotency_key == body.idempotency_key)
    )
    if existing is not None:
        return _receipt(existing)

    payment, _ = _apply(db, device, body)
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        # Two requests with the same key raced; the loser replays the winner's row.
        db.rollback()
        replay = db.scalar(
            select(Payment).where(Payment.idempotency_key == body.idempotency_key)
        )
        if replay is None:
            raise HTTPException(status_code=409, detail="E_CONFLICT")
        return _receipt(replay)
    db.refresh(payment)
    return _receipt(payment)


@router.get("", response_model=list[HistoryItem])
def history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
) -> list[HistoryItem]:
    rows = db.scalars(
        select(Payment)
        .where(or_(Payment.sender_id == device.id, Payment.receiver_id == device.id))
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    out: list[HistoryItem] = []
    for payment in rows:
        outbound = payment.sender_id == device.id
        other_id = payment.receiver_id if outbound else payment.sender_id
        other = db.get(Device, other_id) if other_id else None
        out.append(
            HistoryItem(
                transaction_id=payment.id,
                direction="OUT" if outbound else "IN",
                counterparty=other.name if other else payment.receiver_token48,
                counterparty_token48=(
                    other.token48 if other else payment.receiver_token48
                ),
                amount_cents=payment.amount_cents,
                status=payment.status,  # type: ignore[arg-type]
                memo=payment.memo,
                created_at=iso(payment.created_at),
            )
        )
    return out


@router.post("/batch-sync", response_model=BatchResponse)
def batch_sync(
    body: BatchRequest,
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
) -> BatchResponse:
    """Settle payments queued while the device was offline."""
    accepted: list[BatchItemResult] = []
    declined: list[BatchItemResult] = []

    for item in body.items:
        existing = db.scalar(
            select(Payment).where(Payment.idempotency_key == item.idempotency_key)
        )
        if existing is not None:
            entry = BatchItemResult(
                transaction_id=existing.id,
                status=existing.status,  # type: ignore[arg-type]
                reason_code=existing.reason_code,
            )
            (accepted if existing.status == "COMPLETED" else declined).append(entry)
            continue

        payment, ok = _apply(db, device, item)
        db.add(payment)
        db.flush()
        entry = BatchItemResult(
            transaction_id=payment.id,
            status=payment.status,  # type: ignore[arg-type]
            reason_code=payment.reason_code,
        )
        (accepted if ok else declined).append(entry)

    db.commit()
    return BatchResponse(accepted=accepted, declined=declined)
