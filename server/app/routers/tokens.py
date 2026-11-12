"""Receipt-token verification (offline-provable receipts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_device
from ..models import Device
from ..schemas import TokenVerifyRequest, TokenVerifyResponse
from ..tokens import decode_token48, verify_token48

router = APIRouter(prefix="/api/v1/tokens", tags=["tokens"])


@router.post("/verify", response_model=TokenVerifyResponse)
def verify_token(
    body: TokenVerifyRequest,
    device: Device = Depends(get_device),
) -> TokenVerifyResponse:
    ok, reason = verify_token48(body.token48)
    return TokenVerifyResponse(
        valid=ok,
        reason=reason,
        parts=decode_token48(body.token48) if ok else None,
    )
