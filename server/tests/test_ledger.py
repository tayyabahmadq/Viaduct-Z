"""Double-entry journal: written on settlement, repairable, reconcilable."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.backfill import backfill_ledger
from app.db import SessionLocal
from app.models import LedgerEntry


def _payment_body(receiver: dict, amount: int, key: str | None = None) -> dict:
    return {
        "to_token48": receiver["token48"],
        "amount_cents": amount,
        "idempotency_key": key or f"ledger-{uuid.uuid4()}",
    }


def _entries_for(payment_id: str) -> list[LedgerEntry]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.payment_id == payment_id)
                .order_by(LedgerEntry.direction)
            ).all()
        )


def test_settled_payment_writes_a_balanced_pair(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")

    receipt = client.post(
        "/api/v1/payments", json=_payment_body(bob, 45000), headers=auth(alice)
    ).json()
    assert receipt["status"] == "COMPLETED"

    entries = _entries_for(receipt["transaction_id"])
    assert len(entries) == 2

    debit = next(e for e in entries if e.direction == "DEBIT")
    credit = next(e for e in entries if e.direction == "CREDIT")
    assert debit.device_id == alice["device_id"]
    assert credit.device_id == bob["device_id"]
    assert debit.amount_cents == credit.amount_cents == 45000


def test_declined_payment_writes_no_journal_rows(client, register, auth):
    alice = register("Alice")

    receipt = client.post(
        "/api/v1/payments", json=_payment_body(alice, 1000), headers=auth(alice)
    ).json()
    assert receipt["status"] == "DECLINED"

    assert _entries_for(receipt["transaction_id"]) == []


def test_idempotent_replay_does_not_duplicate_journal_rows(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    key = "ledger-replay-key"

    first = client.post(
        "/api/v1/payments", json=_payment_body(bob, 1000, key), headers=auth(alice)
    ).json()
    client.post(
        "/api/v1/payments", json=_payment_body(bob, 1000, key), headers=auth(alice)
    )

    assert len(_entries_for(first["transaction_id"])) == 2


def test_batch_sync_journals_each_accepted_item(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")

    body = client.post(
        "/api/v1/payments/batch-sync",
        json={
            "items": [
                _payment_body(bob, 1000, "ledger-batch-ok"),
                _payment_body(bob, 600000, "ledger-batch-bad"),
            ]
        },
        headers=auth(alice),
    ).json()

    assert len(body["accepted"]) == 1
    assert len(body["declined"]) == 1
    assert len(_entries_for(body["accepted"][0]["transaction_id"])) == 2
    assert _entries_for(body["declined"][0]["transaction_id"]) == []


def test_summary_is_balanced_after_activity(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    client.post("/api/v1/payments", json=_payment_body(bob, 2500), headers=auth(alice))
    client.post("/api/v1/payments", json=_payment_body(alice, 2500), headers=auth(bob))

    summary = client.get("/api/v1/ledger/summary", headers=auth(alice))
    assert summary.status_code == 200
    body = summary.json()
    assert body["balanced"] is True
    assert body["completed_payments"] == 2
    assert body["journal_entries"] == 4
    assert body["total_debits"] == body["total_credits"] == 5000
    assert body["missing_entries"] == 0


def test_summary_requires_auth(client):
    assert client.get("/api/v1/ledger/summary").status_code == 401


def test_backfill_repairs_a_missing_leg(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    receipt = client.post(
        "/api/v1/payments", json=_payment_body(bob, 1234), headers=auth(alice)
    ).json()

    # Simulate a legacy/corrupted journal by deleting one leg.
    with SessionLocal() as db:
        credit = db.scalar(
            select(LedgerEntry).where(
                LedgerEntry.payment_id == receipt["transaction_id"],
                LedgerEntry.direction == "CREDIT",
            )
        )
        assert credit is not None
        db.delete(credit)
        db.commit()

    broken = client.get("/api/v1/ledger/summary", headers=auth(alice)).json()
    assert broken["balanced"] is False
    assert broken["missing_entries"] == 1

    with SessionLocal() as db:
        assert backfill_ledger(db) == 1

    repaired = client.get("/api/v1/ledger/summary", headers=auth(alice)).json()
    assert repaired["balanced"] is True
    assert repaired["missing_entries"] == 0
    assert repaired["journal_entries"] == 2


def test_backfill_is_idempotent(client, register, auth):
    alice = register("Alice")
    bob = register("Bob")
    client.post("/api/v1/payments", json=_payment_body(bob, 500), headers=auth(alice))

    with SessionLocal() as db:
        assert backfill_ledger(db) == 0

    summary = client.get("/api/v1/ledger/summary", headers=auth(alice)).json()
    assert summary["balanced"] is True
