"""Wallet top-ups funded through PayPal's sandbox."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_device, get_paypal
from ..models import Device, TopUp, new_id, utcnow
from ..paypal import PayPalClient, PayPalError
from ..schemas import (
    PayPalCaptureOut,
    PayPalCaptureRequest,
    PayPalOrderOut,
    PayPalOrderRequest,
    TopUpOut,
)

router = APIRouter(prefix="/api/v1/topups", tags=["topups"])


@router.post("/paypal/order", response_model=PayPalOrderOut)
async def create_paypal_order(
    body: PayPalOrderRequest,
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> PayPalOrderOut:
    if not paypal.configured:
        raise HTTPException(status_code=503, detail="E_PAYPAL_NOT_CONFIGURED")

    settings = get_settings()
    topup_id = new_id()
    return_url = f"{settings.public_base_url}/paypal/return"

    try:
        order = await paypal.create_order(
            amount_cents=body.amount_cents,
            reference=topup_id,
            return_url=return_url,
            cancel_url=return_url,
        )
    except PayPalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    db.add(
        TopUp(
            id=topup_id,
            device_id=device.id,
            provider="paypal",
            order_id=order.id,
            amount_cents=body.amount_cents,
            currency=paypal.currency,
            status="CREATED",
            created_at=utcnow(),
        )
    )
    db.commit()

    return PayPalOrderOut(
        order_id=order.id,
        approve_url=order.approve_url,
        amount_cents=body.amount_cents,
        currency=paypal.currency,
        status=order.status,
    )


@router.post("/paypal/capture", response_model=PayPalCaptureOut)
async def capture_paypal_order(
    body: PayPalCaptureRequest,
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> PayPalCaptureOut:
    topup = db.scalar(
        select(TopUp).where(
            TopUp.order_id == body.order_id, TopUp.device_id == device.id
        )
    )
    if topup is None:
        raise HTTPException(status_code=404, detail="E_TOPUP_NOT_FOUND")

    # Capturing twice must not credit twice.
    if topup.status == "COMPLETED":
        return PayPalCaptureOut(
            status="COMPLETED",
            order_id=topup.order_id,
            capture_id=topup.capture_id,
            amount_cents=topup.amount_cents,
            balance_cents=device.balance_cents,
        )

    if not paypal.configured:
        raise HTTPException(status_code=503, detail="E_PAYPAL_NOT_CONFIGURED")

    try:
        capture = await paypal.capture_order(body.order_id)
    except PayPalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    locked = db.scalar(
        select(Device).where(Device.id == device.id).with_for_update()
    )
    if locked is None:
        raise HTTPException(status_code=404, detail="E_UNKNOWN_PEER")
    locked.balance_cents += capture.amount_cents

    topup.status = "COMPLETED"
    topup.capture_id = capture.capture_id
    topup.amount_cents = capture.amount_cents
    topup.currency = capture.currency
    topup.completed_at = utcnow()
    db.commit()

    return PayPalCaptureOut(
        status="COMPLETED",
        order_id=topup.order_id,
        capture_id=capture.capture_id,
        amount_cents=capture.amount_cents,
        balance_cents=locked.balance_cents,
    )


@router.get("", response_model=list[TopUpOut])
def list_topups(
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
) -> list[TopUpOut]:
    rows = db.scalars(
        select(TopUp)
        .where(TopUp.device_id == device.id)
        .order_by(TopUp.created_at.desc())
        .limit(50)
    ).all()
    return [
        TopUpOut(
            order_id=row.order_id,
            status=row.status,
            amount_cents=row.amount_cents,
            currency=row.currency,
            created_at=row.created_at.replace(microsecond=0).isoformat() + "Z",
            completed_at=(
                row.completed_at.replace(microsecond=0).isoformat() + "Z"
                if row.completed_at
                else None
            ),
        )
        for row in rows
    ]
