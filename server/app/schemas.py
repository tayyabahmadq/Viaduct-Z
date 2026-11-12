"""Request/response models (Pydantic v2)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

PaymentStatus = Literal["COMPLETED", "DECLINED"]


class RegisterRequest(BaseModel):
    device_id: Optional[str] = Field(default=None, max_length=36)
    name: Optional[str] = Field(default=None, max_length=64)


class AccountOut(BaseModel):
    device_id: str
    name: str
    token: str
    token48: str
    balance_cents: int
    credit_ceiling_cents: int
    seq: int
    created_at: str


class PeerOut(BaseModel):
    device_id: str
    name: str
    token48: str
    online: bool
    last_seen_at: str


class PaymentRequest(BaseModel):
    to_token48: str = Field(min_length=48, max_length=48, pattern=r"^\d{48}$")
    amount_cents: int = Field(gt=0, le=10_000_000)
    memo: Optional[str] = Field(default=None, max_length=140)
    idempotency_key: str = Field(min_length=8, max_length=64)


class Receipt(BaseModel):
    status: PaymentStatus
    transaction_id: str
    amount_cents: int
    token48: Optional[str] = None
    sender_balance: int
    receiver_balance: int
    reason_code: Optional[str] = None


class HistoryItem(BaseModel):
    transaction_id: str
    direction: Literal["IN", "OUT"]
    counterparty: str
    counterparty_token48: str
    amount_cents: int
    status: PaymentStatus
    memo: Optional[str] = None
    created_at: str


class BatchRequest(BaseModel):
    items: List[PaymentRequest] = Field(max_length=100)


class BatchItemResult(BaseModel):
    transaction_id: str
    status: PaymentStatus
    reason_code: Optional[str] = None


class BatchResponse(BaseModel):
    accepted: List[BatchItemResult]
    declined: List[BatchItemResult]


class TokenVerifyRequest(BaseModel):
    token48: str = Field(min_length=1, max_length=64)


class TokenVerifyResponse(BaseModel):
    valid: bool
    reason: str
    parts: Optional[dict] = None


class PayPalOrderRequest(BaseModel):
    amount_cents: int = Field(ge=100, le=100_000)


class PayPalOrderOut(BaseModel):
    order_id: str
    approve_url: Optional[str] = None
    amount_cents: int
    currency: str
    status: str


class PayPalCaptureRequest(BaseModel):
    order_id: str = Field(min_length=4, max_length=64)


class PayPalCaptureOut(BaseModel):
    status: Literal["COMPLETED", "DECLINED"]
    order_id: str
    capture_id: Optional[str] = None
    amount_cents: int
    balance_cents: int
    reason_code: Optional[str] = None


class AssistantRequest(BaseModel):
    text: str = Field(min_length=3, max_length=280)


class AssistantOut(BaseModel):
    action: Literal["PAY", "UNKNOWN"]
    receiver_name: Optional[str] = None
    token48: Optional[str] = None
    amount_cents: Optional[int] = None
    memo: Optional[str] = None
    confidence: float
    source: Literal["model", "rules"]
    explanation: str


class TopUpOut(BaseModel):
    order_id: str
    status: str
    amount_cents: int
    currency: str
    created_at: str
    completed_at: Optional[str] = None
