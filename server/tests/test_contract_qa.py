"""Independent contract suite, adapted from the F4 QA module.

F4 shipped with four contract mismatches against the pinned API, all fixed
here (see 11_LOCAL_FIX_HANDOFF §3-F4):

* decline is `200 + status: DECLINED + reason_code`, not 4xx;
* a receipt's success status is `COMPLETED`, not `accepted`;
* history carries `counterparty_token48`, not `token48`;
* `batch-sync` returns `accepted`/`declined` lists of result objects, not ints.

Two F4 cases are deliberately not ported because they assume behaviour the
contract does not have: amount-triggered `E_GUARDRAIL_BLOCKED` and a quarantine
seed endpoint. `test_quarantine_is_not_part_of_the_pinned_contract` records the
first explicitly instead of silently deleting it.
"""

from __future__ import annotations

import uuid

import pytest

from app.tokens import verify_token48


def _key(prefix: str = "qa") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _auth(account: dict) -> dict:
    return {"Authorization": f"Bearer {account['token']}"}


def _register(client, name: str | None = None) -> dict:
    response = client.post(
        "/api/v1/devices/register",
        json={"name": name or f"qa-{uuid.uuid4().hex[:10]}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _pay(client, sender: dict, receiver_token48: str, amount: int, key: str | None = None):
    return client.post(
        "/api/v1/payments",
        json={
            "to_token48": receiver_token48,
            "amount_cents": amount,
            "idempotency_key": key or _key(),
        },
        headers=_auth(sender),
    )


def test_account_contract(client):
    account = _register(client, "qa-account")
    assert set(account) == {
        "device_id",
        "name",
        "token",
        "token48",
        "balance_cents",
        "credit_ceiling_cents",
        "seq",
        "created_at",
    }
    assert verify_token48(account["token48"]) == (True, "OK")

    me = client.get("/api/v1/me", headers=_auth(account))
    assert me.status_code == 200
    assert me.json()["token48"] == account["token48"]


def test_peer_and_resolve_contract(client):
    sender = _register(client, "qa-peer-sender")
    receiver = _register(client, "qa-peer-receiver")

    peers = client.get(
        "/api/v1/peers", params={"q": receiver["name"]}, headers=_auth(sender)
    )
    assert peers.status_code == 200
    assert all(set(peer) == {"device_id", "name", "token48", "online", "last_seen_at"} for peer in peers.json())
    assert any(peer["token48"] == receiver["token48"] for peer in peers.json())

    resolved = client.get(
        "/api/v1/peers/resolve", params={"token48": receiver["token48"]}
    )
    assert resolved.status_code == 200
    assert resolved.json()["device_id"] == receiver["device_id"]


def test_receipt_and_history_contract(client):
    sender = _register(client, "qa-receipt-sender")
    receiver = _register(client, "qa-receipt-receiver")

    response = _pay(client, sender, receiver["token48"], 123, "qa-happy")
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["status"] == "COMPLETED"
    assert set(receipt) >= {
        "status",
        "transaction_id",
        "amount_cents",
        "token48",
        "sender_balance",
        "receiver_balance",
    }
    assert verify_token48(receipt["token48"]) == (True, "OK")
    assert receipt["sender_balance"] == sender["balance_cents"] - 123
    assert receipt["receiver_balance"] == receiver["balance_cents"] + 123

    items = client.get(
        "/api/v1/payments", params={"limit": 10}, headers=_auth(sender)
    ).json()
    matching = next(i for i in items if i["transaction_id"] == receipt["transaction_id"])
    assert "counterparty_token48" in matching
    assert "token48" not in matching
    assert matching["direction"] == "OUT"


def test_declines_are_recorded_not_http_errors(client):
    sender = _register(client, "qa-decline-sender")
    receiver = _register(client, "qa-decline-receiver")

    cases = [
        (sender["token48"], 1, "E_SELF_PAY"),
        (receiver["token48"], sender["credit_ceiling_cents"] + 1, "E_CEILING_EXCEEDED"),
        (receiver["token48"], sender["balance_cents"] + 1, "E_INSUFFICIENT_BALANCE"),
    ]
    for token48, amount, expected in cases:
        response = _pay(client, sender, token48, amount)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "DECLINED"
        assert body["reason_code"] == expected
        assert body["token48"] is None

    unknown = "0" * 44 + "0000"
    response = _pay(client, sender, unknown, 1)
    assert response.status_code == 200
    assert response.json()["reason_code"] == "E_UNKNOWN_PEER"


def test_malformed_payload_is_validation_422(client):
    sender = _register(client, "qa-malformed")
    for payload in (
        {"to_token48": "not-a-token", "amount_cents": 1, "idempotency_key": _key("bad")},
        {"to_token48": "0" * 48, "amount_cents": -1, "idempotency_key": _key("bad")},
        {"to_token48": "0" * 48, "amount_cents": 1, "idempotency_key": "short"},
    ):
        response = client.post(
            "/api/v1/payments", json=payload, headers=_auth(sender)
        )
        assert response.status_code == 422, payload


def test_idempotent_replay_with_a_different_payload_returns_the_first_receipt(client):
    sender = _register(client, "qa-idem-sender")
    receiver = _register(client, "qa-idem-receiver")
    key = _key("idem")

    first = _pay(client, sender, receiver["token48"], 10, key).json()
    second = _pay(client, sender, receiver["token48"], 20, key).json()

    # The contract prefers replay over conflict: the stored receipt wins.
    assert second == first
    assert second["amount_cents"] == 10


def test_batch_contract_returns_result_objects(client):
    sender = _register(client, "qa-batch-sender")
    receiver = _register(client, "qa-batch-receiver")

    body = client.post(
        "/api/v1/payments/batch-sync",
        json={
            "items": [
                {
                    "to_token48": receiver["token48"],
                    "amount_cents": 1,
                    "idempotency_key": _key("batch-ok"),
                },
                {
                    "to_token48": receiver["token48"],
                    "amount_cents": sender["credit_ceiling_cents"] + 1,
                    "idempotency_key": _key("batch-bad"),
                },
            ]
        },
        headers=_auth(sender),
    ).json()

    assert len(body["accepted"]) == 1
    assert len(body["declined"]) == 1
    assert set(body["accepted"][0]) == {"transaction_id", "status", "reason_code"}
    assert body["declined"][0]["reason_code"] == "E_CEILING_EXCEEDED"


def test_token_verify_round_trip(client):
    sender = _register(client, "qa-token")
    body = client.post(
        "/api/v1/tokens/verify",
        json={"token48": sender["token48"]},
        headers=_auth(sender),
    ).json()
    assert body["valid"] is True
    assert body["reason"] == "OK"


@pytest.mark.skip(
    reason="The pinned contract has no quarantine surface; E_QUARANTINED_PEER is "
    "only reachable through guard.screen() fixtures, not the HTTP API."
)
def test_quarantine_is_not_part_of_the_pinned_contract(client):
    ...
