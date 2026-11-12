"""FastAPI dependencies — bearer authentication."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Device, utcnow
from .assistant import PaymentAssistant
from .config import get_settings
from .paypal import PayPalClient


def get_device(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Device:
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    device = db.scalar(select(Device).where(Device.api_token == token))
    if device is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    device.last_seen_at = utcnow()
    db.commit()
    return device


def get_paypal() -> PayPalClient:
    settings = get_settings()
    return PayPalClient(
        client_id=settings.paypal_client_id,
        client_secret=settings.paypal_client_secret,
        base_url=settings.paypal_base_url,
        currency=settings.paypal_currency,
    )


def get_assistant() -> PaymentAssistant:
    settings = get_settings()
    return PaymentAssistant(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
        model=settings.ai_model,
    )
