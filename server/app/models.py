"""SQLAlchemy models for the demo ledger."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    """Naive UTC, so SQLite and Postgres store identical values."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


def iso(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat() + "Z"


class Device(Base):
    """A wallet. `token48` is the public payment address, `api_token` the credential."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    short_hash: Mapped[str] = mapped_column(String(4), unique=True, index=True)
    token48: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    api_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    credit_ceiling_cents: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint("balance_cents >= 0", name="ck_device_balance_non_negative"),
        CheckConstraint("credit_ceiling_cents >= 0", name="ck_device_ceiling_non_negative"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sender_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    # NULL once the receiver is deleted; receiver_token48 keeps the audit trail.
    receiver_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), index=True, nullable=True
    )
    receiver_token48: Mapped[str] = mapped_column(String(48), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(String(140), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nonce: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    token48: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sender_balance_after: Mapped[int] = mapped_column(Integer, default=0)
    receiver_balance_after: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_payment_amount_positive"),
        CheckConstraint(
            "status IN ('COMPLETED', 'DECLINED')", name="ck_payment_status_values"
        ),
    )


class TopUp(Base):
    """A wallet top-up funded through PayPal's sandbox."""

    __tablename__ = "topups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16), default="paypal")
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    capture_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(16), default="CREATED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_topup_amount_positive"),
        CheckConstraint(
            "status IN ('CREATED', 'COMPLETED', 'FAILED')",
            name="ck_topup_status_values",
        ),
    )
