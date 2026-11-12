"""Peer directory: who you can pay."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import get_device
from ..models import Device, iso, utcnow
from ..schemas import PeerOut

router = APIRouter(prefix="/api/v1", tags=["peers"])


def _peer_out(device: Device) -> PeerOut:
    age = (utcnow() - device.last_seen_at).total_seconds()
    return PeerOut(
        device_id=device.id,
        name=device.name,
        token48=device.token48,
        online=age <= get_settings().peer_online_seconds,
        last_seen_at=iso(device.last_seen_at),
    )


@router.get("/peers", response_model=list[PeerOut])
def list_peers(
    q: Optional[str] = None,
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
) -> list[PeerOut]:
    stmt = select(Device).where(Device.id != device.id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Device.name.ilike(like), Device.token48.like(like)))
    rows = db.scalars(stmt.order_by(Device.last_seen_at.desc()).limit(50)).all()
    return [_peer_out(row) for row in rows]


@router.get("/peers/resolve", response_model=PeerOut)
def resolve(token48: str, db: Session = Depends(get_db)) -> PeerOut:
    device = db.scalar(select(Device).where(Device.token48 == token48))
    if device is None:
        raise HTTPException(status_code=404, detail="E_UNKNOWN_PEER")
    return _peer_out(device)
