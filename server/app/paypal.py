"""PayPal Orders v2 client, pointed at the sandbox by default.

Only two calls are used:

* `POST /v2/checkout/orders`   — create a CAPTURE order, get the approval URL
* `POST /v2/checkout/orders/{id}/capture` — take the money in sandbox

Authentication is OAuth2 client-credentials (`/v1/oauth2/token`), so the app
never sees the client secret.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

import httpx


class PayPalError(RuntimeError):
    def __init__(self, message: str, code: str = "E_PAYPAL", status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def cents_to_amount(cents: int) -> str:
    return str(
        (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def amount_to_cents(value: str) -> int:
    return int(
        (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


@dataclass(frozen=True)
class PayPalOrder:
    id: str
    status: str
    approve_url: Optional[str]


@dataclass(frozen=True)
class PayPalCapture:
    order_id: str
    capture_id: str
    amount_cents: int
    currency: str
    status: str


class PayPalClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str,
        currency: str = "USD",
        timeout: float = 20.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.currency = currency
        self.timeout = timeout
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self.transport)

    async def _access_token(self) -> str:
        if not self.configured:
            raise PayPalError(
                "PayPal credentials are not configured",
                "E_PAYPAL_NOT_CONFIGURED",
                503,
            )
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("ascii")
        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
            )
        if response.status_code >= 400:
            raise self._error(response)
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise PayPalError("PayPal returned no access token", "E_PAYPAL_AUTH", 502)
        return str(token)

    async def create_order(
        self,
        amount_cents: int,
        reference: str,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> PayPalOrder:
        token = await self._access_token()
        body: dict[str, Any] = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference,
                    "description": "Viaduct Pay demo wallet top-up",
                    "amount": {
                        "currency_code": self.currency,
                        "value": cents_to_amount(amount_cents),
                    },
                }
            ],
        }
        if return_url:
            body["application_context"] = {
                "brand_name": "Viaduct Pay",
                "user_action": "PAY_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url or return_url,
            }

        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    # PayPal treats this as an idempotency key.
                    "PayPal-Request-Id": reference,
                    "Prefer": "return=representation",
                },
                json=body,
            )
        if response.status_code >= 400:
            raise self._error(response)

        payload = response.json()
        links = payload.get("links") or []
        approve_url = next(
            (
                link.get("href")
                for link in links
                if link.get("rel") in ("approve", "payer-action")
            ),
            None,
        )
        order_id = payload.get("id")
        if not order_id:
            raise PayPalError("PayPal returned no order id", "E_PAYPAL_ORDER", 502)
        return PayPalOrder(
            id=str(order_id),
            status=str(payload.get("status", "CREATED")),
            approve_url=approve_url,
        )

    async def capture_order(self, order_id: str) -> PayPalCapture:
        token = await self._access_token()
        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": f"capture-{order_id}",
                    "Prefer": "return=representation",
                },
                json={},
            )
        if response.status_code >= 400:
            raise self._error(response)

        payload = response.json()
        status = str(payload.get("status", ""))
        units = payload.get("purchase_units") or [{}]
        captures = ((units[0].get("payments") or {}).get("captures")) or []
        capture = captures[0] if captures else {}
        capture_id = capture.get("id")
        amount = capture.get("amount") or {}

        if status != "COMPLETED" or not capture_id:
            raise PayPalError(
                f"PayPal did not complete the capture (status={status or 'unknown'})",
                "E_PAYPAL_CAPTURE_INCOMPLETE",
                502,
            )

        return PayPalCapture(
            order_id=order_id,
            capture_id=str(capture_id),
            amount_cents=amount_to_cents(str(amount.get("value", "0"))),
            currency=str(amount.get("currency_code", self.currency)),
            status=status,
        )

    @staticmethod
    def _error(response: httpx.Response) -> PayPalError:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        name = str(payload.get("name") or "E_PAYPAL_HTTP")
        message = str(payload.get("message") or response.text[:200])
        return PayPalError(f"{name}: {message}", name, 502)
