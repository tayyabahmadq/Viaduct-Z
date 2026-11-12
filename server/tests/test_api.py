"""End-to-end API behaviour against a real (SQLite) database."""

from __future__ import annotations

import uuid

from app.tokens import build_token48, decode_token48, make_nonce, verify_token48


def _payment(receiver: dict, amount: int, key: str | None = None) -> dict:
    return {
        "to_token48": receiver["token48"],
        "amount_cents": amount,
        "idempotency_key": key or f"key-{uuid.uuid4()}",
    }

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_returns_wallet_with_48_digit_token(client):
    response = client.post("/api/v1/devices/register", json={"name": "Alice"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Alice"
    assert body["balance_cents"] == 250000
    assert body["credit_ceiling_cents"] == 500000
    assert len(body["token48"]) == 48 and body["token48"].isdigit()
    assert body["token"]


def test_register_is_idempotent_for_a_device_id(client):
    device_id = str(uuid.uuid4())
    first = client.post(
        "/api/v1/devices/register", json={"device_id": device_id, "name": "Alice"}
    ).json()
    second = client.post(
        "/api/v1/devices/register", json={"device_id": device_id, "name": "Alice"}
    ).json()
    assert first["device_id"] == second["device_id"]
    assert first["token48"] == second["token48"]
    assert first["token"] == second["token"]


def test_me_requires_bearer_token(client, register, auth):
    alice = register("Alice")
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer nope"}).status_code == 401

    response = client.get("/api/v1/me", headers=auth(alice))
    assert response.status_code == 200
    assert response.json()["device_id"] == alice["device_id"]


def test_peers_exclude_caller(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    response = client.get("/api/v1/peers", headers=auth(alice))
    assert response.status_code == 200
    ids = [peer["device_id"] for peer in response.json()]
    assert bob["device_id"] in ids
    assert alice["device_id"] not in ids


def test_peer_resolve_by_token(client, register):
    bob = register("Bob")
    response = client.get("/api/v1/peers/resolve", params={"token48": bob["token48"]})
    assert response.status_code == 200
    assert response.json()["device_id"] == bob["device_id"]


def test_resolve_unknown_token_is_404(client):
    unknown = build_token48("9999", "9999", 0, 0, make_nonce())
    assert client.get("/api/v1/peers/resolve", params={"token48": unknown}).status_code == 404


def test_payment_moves_money_and_issues_a_valid_token(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")

    response = client.post(
        "/api/v1/payments", json=_payment(bob, 45000), headers=auth(alice)
    )
    assert response.status_code == 200, response.text
    receipt = response.json()

    assert receipt["status"] == "COMPLETED"
    assert receipt["sender_balance"] == 205000
    assert receipt["receiver_balance"] == 295000
    assert receipt["reason_code"] is None
    assert verify_token48(receipt["token48"]) == (True, "OK")

    parts = decode_token48(receipt["token48"])
    assert parts is not None
    assert parts["amount_cents"] == 45000

    assert client.get("/api/v1/me", headers=auth(alice)).json()["balance_cents"] == 205000
    assert client.get("/api/v1/me", headers=auth(bob)).json()["balance_cents"] == 295000


def test_idempotent_replay_returns_identical_receipt(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    key = "fixed-idempotency-key"

    first = client.post(
        "/api/v1/payments", json=_payment(bob, 45000, key), headers=auth(alice)
    ).json()
    second = client.post(
        "/api/v1/payments", json=_payment(bob, 45000, key), headers=auth(alice)
    ).json()

    assert first == second
    assert client.get("/api/v1/me", headers=auth(alice)).json()["balance_cents"] == 205000


def test_self_payment_is_declined(client, register, auth):
    alice = register("Alice")
    response = client.post(
        "/api/v1/payments", json=_payment(alice, 1000), headers=auth(alice)
    )
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["status"] == "DECLINED"
    assert receipt["reason_code"] == "E_SELF_PAY"
    assert receipt["token48"] is None
    assert client.get("/api/v1/me", headers=auth(alice)).json()["balance_cents"] == 250000


def test_amount_above_ceiling_is_declined(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    receipt = client.post(
        "/api/v1/payments", json=_payment(bob, 500001), headers=auth(alice)
    ).json()
    assert receipt["status"] == "DECLINED"
    assert receipt["reason_code"] == "E_CEILING_EXCEEDED"


def test_amount_above_balance_is_declined(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    receipt = client.post(
        "/api/v1/payments", json=_payment(bob, 300000), headers=auth(alice)
    ).json()
    assert receipt["status"] == "DECLINED"
    assert receipt["reason_code"] == "E_INSUFFICIENT_BALANCE"


def test_unknown_peer_is_declined(client, register, auth):
    alice = register("Alice")
    phantom = {"token48": build_token48("7777", "8888", 0, 0, make_nonce())}

    receipt = client.post(
        "/api/v1/payments", json=_payment(phantom, 1000), headers=auth(alice)
    ).json()
    assert receipt["status"] == "DECLINED"
    assert receipt["reason_code"] == "E_UNKNOWN_PEER"


def test_payment_requires_auth(client, register):
    bob = register("Bob")
    response = client.post("/api/v1/payments", json=_payment(bob, 1000))
    assert response.status_code == 401


def test_receipt_is_not_reachable_without_bearer(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    client.post("/api/v1/payments", json=_payment(bob, 1000), headers=auth(alice))
    assert client.get("/api/v1/payments").status_code == 401


def test_history_shows_both_sides(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    client.post("/api/v1/payments", json=_payment(bob, 45000), headers=auth(alice))

    alice_history = client.get("/api/v1/payments", headers=auth(alice)).json()
    bob_history = client.get("/api/v1/payments", headers=auth(bob)).json()

    assert alice_history[0]["direction"] == "OUT"
    assert alice_history[0]["counterparty"] == "Bob"
    assert alice_history[0]["amount_cents"] == 45000
    assert alice_history[0]["status"] == "COMPLETED"

    assert bob_history[0]["direction"] == "IN"
    assert bob_history[0]["counterparty"] == "Alice"


def test_declined_payment_appears_in_history(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    client.post("/api/v1/payments", json=_payment(bob, 500001), headers=auth(alice))

    history = client.get("/api/v1/payments", headers=auth(alice)).json()
    assert history[0]["status"] == "DECLINED"
    assert history[0]["amount_cents"] == 500001


def test_batch_sync_mixes_accepted_and_declined(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    payload = {
        "items": [
            {
                "to_token48": bob["token48"],
                "amount_cents": 1000,
                "idempotency_key": "batch-ok-1",
            },
            {
                "to_token48": bob["token48"],
                "amount_cents": 600000,
                "idempotency_key": "batch-bad-1",
            },
        ]
    }
    response = client.post("/api/v1/payments/batch-sync", json=payload, headers=auth(alice))
    assert response.status_code == 200
    body = response.json()
    assert len(body["accepted"]) == 1
    assert len(body["declined"]) == 1
    assert body["declined"][0]["reason_code"] == "E_CEILING_EXCEEDED"
    assert client.get("/api/v1/me", headers=auth(alice)).json()["balance_cents"] == 249000


def test_batch_sync_replays_without_double_spending(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    payload = {
        "items": [
            {
                "to_token48": bob["token48"],
                "amount_cents": 1000,
                "idempotency_key": "batch-replay-1",
            }
        ]
    }
    first = client.post("/api/v1/payments/batch-sync", json=payload, headers=auth(alice)).json()
    second = client.post("/api/v1/payments/batch-sync", json=payload, headers=auth(alice)).json()
    assert first["accepted"][0]["transaction_id"] == second["accepted"][0]["transaction_id"]
    assert client.get("/api/v1/me", headers=auth(alice)).json()["balance_cents"] == 249000


def test_token_verification_endpoint(client, register, auth):
    alice = register("Alice")
    valid = build_token48("0001", "0002", 45000, 3, make_nonce())

    good = client.post(
        "/api/v1/tokens/verify", json={"token48": valid}, headers=auth(alice)
    ).json()
    assert good["valid"] is True
    assert good["parts"]["amount_cents"] == 45000

    tampered = valid[:44] + ("0000" if valid[44:] != "0000" else "0001")
    bad = client.post(
        "/api/v1/tokens/verify", json={"token48": tampered}, headers=auth(alice)
    ).json()
    assert bad["valid"] is False
    assert bad["reason"] == "E_TOKEN_CHECKSUM"


def test_rate_limit_declines_the_twenty_first_payment(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    statuses = []
    for _ in range(21):
        receipt = client.post(
            "/api/v1/payments", json=_payment(bob, 100), headers=auth(alice)
        ).json()
        statuses.append(receipt.get("reason_code"))

    assert statuses[:20] == [None] * 20
    assert statuses[20] == "E_RATE_LIMIT"
