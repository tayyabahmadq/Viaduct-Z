"""PayPal sandbox top-ups and the AI payment assistant."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.assistant import ParsedIntent, PaymentAssistant, parse_rules
from app.deps import get_assistant, get_paypal
from app.main import app
from app.paypal import (
    PayPalCapture,
    PayPalClient,
    PayPalError,
    PayPalOrder,
    amount_to_cents,
    cents_to_amount,
)

PEER = SimpleNamespace(name="Mei Chen", token48="0" * 48)


class FakePayPal:
    configured = True
    currency = "USD"

    def __init__(self, capture_cents: int = 2500, fail: bool = False) -> None:
        self.capture_cents = capture_cents
        self.fail = fail
        self.calls: list[tuple] = []

    async def create_order(self, amount_cents, reference, return_url=None, cancel_url=None):
        self.calls.append(("create", amount_cents, reference))
        if self.fail:
            raise PayPalError("INSTRUMENT_DECLINED: card", "INSTRUMENT_DECLINED")
        return PayPalOrder(
            id="ORDER-1",
            status="CREATED",
            approve_url="https://sandbox.paypal.com/checkoutnow?token=ORDER-1",
        )

    async def capture_order(self, order_id):
        self.calls.append(("capture", order_id))
        if self.fail:
            raise PayPalError("ORDER_ALREADY_CAPTURED: done", "ORDER_ALREADY_CAPTURED")
        return PayPalCapture(
            order_id=order_id,
            capture_id="CAP-1",
            amount_cents=self.capture_cents,
            currency="USD",
            status="COMPLETED",
        )


@pytest.fixture
def fake_paypal():
    fake = FakePayPal()
    app.dependency_overrides[get_paypal] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_paypal, None)


def _order(client, auth, account, amount=2500):
    return client.post(
        "/api/v1/topups/paypal/order",
        json={"amount_cents": amount},
        headers=auth(account),
    )


def test_paypal_is_503_when_not_configured(client, register, auth):
    alice = register("Alice")
    response = _order(client, auth, alice)
    assert response.status_code == 503
    assert response.json()["detail"] == "E_PAYPAL_NOT_CONFIGURED"


def test_paypal_top_up_credits_the_wallet_once(client, register, auth, fake_paypal):
    alice = register("Alice")

    created = _order(client, auth, alice, 2500)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["order_id"] == "ORDER-1"
    assert body["approve_url"].startswith("https://sandbox.paypal.com/")

    captured = client.post(
        "/api/v1/topups/paypal/capture",
        json={"order_id": "ORDER-1"},
        headers=auth(alice),
    )
    assert captured.status_code == 200, captured.text
    assert captured.json()["status"] == "COMPLETED"
    assert captured.json()["amount_cents"] == 2500
    assert captured.json()["balance_cents"] == 252500

    # Replaying the capture must not credit a second time.
    replay = client.post(
        "/api/v1/topups/paypal/capture",
        json={"order_id": "ORDER-1"},
        headers=auth(alice),
    )
    assert replay.status_code == 200
    assert replay.json()["balance_cents"] == 252500
    assert client.get("/api/v1/me", headers=auth(alice)).json()["balance_cents"] == 252500


def test_capture_rejects_another_users_order(client, register, auth, fake_paypal):
    alice = register("Alice")
    bob = register("Bob")
    _order(client, auth, alice)

    response = client.post(
        "/api/v1/topups/paypal/capture",
        json={"order_id": "ORDER-1"},
        headers=auth(bob),
    )
    assert response.status_code == 404


def test_capture_unknown_order_is_404(client, register, auth, fake_paypal):
    alice = register("Alice")
    response = client.post(
        "/api/v1/topups/paypal/capture",
        json={"order_id": "NOPE-1"},
        headers=auth(alice),
    )
    assert response.status_code == 404


def test_paypal_failure_is_502(client, register, auth):
    failing = FakePayPal(fail=True)
    app.dependency_overrides[get_paypal] = lambda: failing
    try:
        alice = register("Alice")
        response = _order(client, auth, alice)
        assert response.status_code == 502
        assert response.json()["detail"] == "INSTRUMENT_DECLINED"
    finally:
        app.dependency_overrides.pop(get_paypal, None)


def test_top_up_history_lists_completed(client, register, auth, fake_paypal):
    alice = register("Alice")
    _order(client, auth, alice)
    client.post(
        "/api/v1/topups/paypal/capture",
        json={"order_id": "ORDER-1"},
        headers=auth(alice),
    )
    history = client.get("/api/v1/topups", headers=auth(alice)).json()
    assert history[0]["order_id"] == "ORDER-1"
    assert history[0]["status"] == "COMPLETED"


def test_amount_helpers_round_trip():
    assert cents_to_amount(2500) == "25.00"
    assert cents_to_amount(5) == "0.05"
    assert amount_to_cents("25.00") == 2500
    assert amount_to_cents("0.05") == 5


def test_paypal_client_sends_the_expected_requests():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/oauth2/token":
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "tok-123"})
        if request.url.path == "/v2/checkout/orders":
            body = json.loads(request.content)
            assert body["intent"] == "CAPTURE"
            assert body["purchase_units"][0]["amount"] == {
                "currency_code": "USD",
                "value": "25.00",
            }
            assert request.headers["PayPal-Request-Id"] == "ref-1"
            assert request.headers["authorization"] == "Bearer tok-123"
            return httpx.Response(
                200,
                json={
                    "id": "O-9",
                    "status": "CREATED",
                    "links": [
                        {"rel": "self", "href": "https://api/x"},
                        {"rel": "approve", "href": "https://paypal/approve"},
                    ],
                },
            )
        if request.url.path == "/v2/checkout/orders/O-9/capture":
            assert request.headers["authorization"] == "Bearer tok-123"
            return httpx.Response(
                200,
                json={
                    "id": "O-9",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "C-9",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "25.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                },
            )
        return httpx.Response(404)

    client = PayPalClient(
        "id",
        "secret",
        "https://api-m.sandbox.paypal.com",
        transport=httpx.MockTransport(handler),
    )

    order = asyncio.run(client.create_order(2500, "ref-1"))
    assert order.id == "O-9"
    assert order.approve_url == "https://paypal/approve"

    capture = asyncio.run(client.capture_order("O-9"))
    assert capture.capture_id == "C-9"
    assert capture.amount_cents == 2500
    assert capture.status == "COMPLETED"
    # A fresh token per call: token, create, token, capture.
    assert [r.url.path for r in seen] == [
        "/v1/oauth2/token",
        "/v2/checkout/orders",
        "/v1/oauth2/token",
        "/v2/checkout/orders/O-9/capture",
    ]


def test_paypal_client_surfaces_api_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(
            422,
            json={"name": "INSTRUMENT_DECLINED", "message": "The card was declined."},
        )

    client = PayPalClient(
        "id", "secret", "https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(PayPalError) as excinfo:
        asyncio.run(client.create_order(2500, "ref-2"))
    assert excinfo.value.code == "INSTRUMENT_DECLINED"


# ------------------------------- assistant -------------------------------


def test_rules_parser_reads_amount_and_peer():
    intent = parse_rules("please send $25.50 to Mei Chen today", [PEER])
    assert intent.action == "PAY"
    assert intent.receiver_name == "Mei Chen"
    assert intent.amount_cents == 2550
    assert intent.source == "rules"


def test_rules_parser_accepts_a_bare_dollar_amount():
    intent = parse_rules("send 40 to Mei Chen", [PEER])
    assert intent.amount_cents == 4000


def test_rules_parser_refuses_an_unknown_recipient():
    intent = parse_rules("send $25 to Nobody At All", [PEER])
    assert intent.action == "UNKNOWN"
    assert intent.amount_cents == 2500


def test_assistant_uses_rules_when_no_model_is_configured(client, register, auth):
    alice = register("Alice")
    mei = register("Mei Chen")

    response = client.post(
        "/api/v1/assistant/parse",
        json={"text": "send $25 to Mei Chen"},
        headers=auth(alice),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action"] == "PAY"
    assert body["source"] == "rules"
    assert body["amount_cents"] == 2500
    assert body["token48"] == mei["token48"]


def test_assistant_uses_the_model_when_configured(client, register, auth):
    alice = register("Alice")
    register("Mei Chen")

    class FakeAssistant:
        configured = True

        async def parse(self, text, peers):
            return ParsedIntent(
                action="PAY",
                receiver_name=peers[0].name,
                token48=peers[0].token48,
                amount_cents=1200,
                memo="lunch",
                confidence=0.93,
                source="model",
                explanation="stubbed model",
            )

    app.dependency_overrides[get_assistant] = lambda: FakeAssistant()
    try:
        body = client.post(
            "/api/v1/assistant/parse",
            json={"text": "cover lunch"},
            headers=auth(alice),
        ).json()
    finally:
        app.dependency_overrides.pop(get_assistant, None)

    assert body["source"] == "model"
    assert body["amount_cents"] == 1200
    assert body["confidence"] == 0.93


def test_assistant_falls_back_when_the_model_returns_junk():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    assistant = PaymentAssistant(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        transport=httpx.MockTransport(handler),
    )
    intent = asyncio.run(assistant.parse("send $30 to Mei Chen", [PEER]))
    assert intent.source == "rules"
    assert intent.amount_cents == 3000


def test_assistant_model_path_parses_json():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "action": "PAY",
            "receiver_name": "Mei Chen",
            "amount_cents": 3300,
            "memo": "rent",
            "confidence": 0.88,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
        )

    assistant = PaymentAssistant(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        transport=httpx.MockTransport(handler),
    )
    intent = asyncio.run(assistant.parse("send 33 to Mei", [PEER]))
    assert intent.source == "model"
    assert intent.amount_cents == 3300
    assert intent.receiver_name == "Mei Chen"
