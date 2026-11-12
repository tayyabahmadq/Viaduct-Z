"""Device registration and the caller's own account."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_device
from ..models import Device, iso, new_id, utcnow
from ..schemas import AccountOut, RegisterRequest
from ..tokens import build_token48, make_nonce, short_hash

router = APIRouter(prefix="/api/v1", tags=["devices"])


def _out(device: Device) -> AccountOut:
    return AccountOut(
        device_id=device.id,
        name=device.name,
        token=device.api_token,
        token48=device.token48,
        balance_cents=device.balance_cents,
        credit_ceiling_cents=device.credit_ceiling_cents,
        seq=device.seq,
        created_at=iso(device.created_at),
    )


def _unique_short(db: Session, seed: str) -> str:
    for attempt in range(200):
        candidate = short_hash(f"{seed}:{attempt}")
        if db.scalar(select(Device.id).where(Device.short_hash == candidate)) is None:
            return candidate
    raise RuntimeError("could not allocate a free short hash")


def _unique_token48(db: Session, short: str) -> str:
    for _ in range(20):
        token = build_token48(short, "0000", 0, 0, make_nonce())
        if db.scalar(select(Device.id).where(Device.token48 == token)) is None:
            return token
    raise RuntimeError("could not allocate a free token48")


@router.post("/devices/register", response_model=AccountOut)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> AccountOut:
    if body.device_id:
        existing = db.get(Device, body.device_id)
        if existing is not None:
            existing.last_seen_at = utcnow()
            db.commit()
            return _out(existing)

    name = (body.name or "Demo user").strip() or "Demo user"
    device_id = body.device_id or new_id()
    short = _unique_short(db, device_id)
    settings = get_settings()

    device = Device(
        id=device_id,
        name=name,
        short_hash=short,
        token48=_unique_token48(db, short),
        api_token=secrets.token_urlsafe(32),
        balance_cents=settings.start_balance_cents,
        credit_ceiling_cents=settings.credit_ceiling_cents,
        seq=0,
        created_at=utcnow(),
        last_seen_at=utcnow(),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return _out(device)


@router.get("/me", response_model=AccountOut)
def me(device: Device = Depends(get_device)) -> AccountOut:
    return _out(device)
