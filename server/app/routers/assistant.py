"""Natural-language payment entry."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..assistant import PaymentAssistant
from ..db import get_db
from ..deps import get_assistant, get_device
from ..models import Device
from ..schemas import AssistantOut, AssistantRequest

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


@router.post("/parse", response_model=AssistantOut)
async def parse(
    body: AssistantRequest,
    device: Device = Depends(get_device),
    db: Session = Depends(get_db),
    assistant: PaymentAssistant = Depends(get_assistant),
) -> AssistantOut:
    peers = db.scalars(
        select(Device)
        .where(Device.id != device.id)
        .order_by(Device.last_seen_at.desc())
        .limit(50)
    ).all()

    intent = await assistant.parse(body.text, peers)

    return AssistantOut(
        action="PAY" if intent.action == "PAY" else "UNKNOWN",
        receiver_name=intent.receiver_name,
        token48=intent.token48,
        amount_cents=intent.amount_cents,
        memo=intent.memo,
        confidence=intent.confidence,
        source="model" if intent.source == "model" else "rules",
        explanation=intent.explanation,
    )
