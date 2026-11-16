"""The pure guard must match `fixtures/guard_fixtures.json` exactly.

The Android `TxGuard.screen()` is a mirror of this function and is checked
against the same file, so the two implementations cannot drift silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.guard import screen

FIXTURES_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "guard_fixtures.json"
)
FIXTURES = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def test_fixture_file_has_at_least_thirty_cases():
    # The canonical 30 are frozen; `scripts/gen_fixtures.py` only appends.
    assert len(FIXTURES) >= 30


def test_fixture_names_are_unique():
    names = [fixture["name"] for fixture in FIXTURES]
    assert len(names) == len(set(names))


MALFORMED_TOKEN_FIXTURES = {
    "token of 47 digits is malformed",
    "non-numeric token is malformed",
}


def test_every_well_formed_token_is_48_digits():
    for fixture in FIXTURES:
        token = fixture["tx"]["token48"]
        if token is None or fixture["name"] in MALFORMED_TOKEN_FIXTURES:
            continue
        assert len(token) == 48, fixture["name"]
        assert token.isdigit(), fixture["name"]


@pytest.mark.parametrize(
    "fixture", FIXTURES, ids=[fixture["name"] for fixture in FIXTURES]
)
def test_fixture_matches(fixture):
    assert screen(fixture["tx"], fixture["state"]) == fixture["expected"]


def test_screen_does_not_mutate_inputs():
    fixture = FIXTURES[0]
    tx = json.loads(json.dumps(fixture["tx"]))
    state = json.loads(json.dumps(fixture["state"]))
    screen(tx, state)
    assert tx == fixture["tx"]
    assert state == fixture["state"]


def test_unknown_fields_do_not_crash():
    decision = screen(
        {
            "sender_account_id": "a",
            "receiver_account_id": "b",
            "amount": 10,
            "nonce": "n",
            "token48": None,
            "timestamp_ms": 1,
        },
        {},
    )
    assert decision["code"] == "E_CEILING_EXCEEDED"
