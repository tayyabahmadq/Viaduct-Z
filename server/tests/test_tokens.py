"""Token layout, checksum and decoding."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tokens import (
    EPOCH,
    build_token48,
    decode_token48,
    make_nonce,
    short_hash,
    verify_token48,
)

FIXED_TS = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
FIXED_NONCE = "12345678901234567890"


def test_token_is_exactly_48_digits():
    token = build_token48("0001", "0002", 45000, 7, FIXED_NONCE, FIXED_TS)
    assert len(token) == 48
    assert token.isdigit()


def test_checksum_validates():
    token = build_token48("0001", "0002", 45000, 7, FIXED_NONCE, FIXED_TS)
    ok, reason = verify_token48(token)
    assert ok is True
    assert reason == "OK"


def test_token_is_deterministic_for_fixed_inputs():
    a = build_token48("0001", "0002", 45000, 7, FIXED_NONCE, FIXED_TS)
    b = build_token48("0001", "0002", 45000, 7, FIXED_NONCE, FIXED_TS)
    assert a == b


def test_decoded_parts_round_trip():
    token = build_token48("0042", "0007", 123456, 9, FIXED_NONCE, FIXED_TS)
    parts = decode_token48(token)
    assert parts is not None
    assert parts["sender_short"] == "0042"
    assert parts["receiver_short"] == "0007"
    assert parts["amount_cents"] == 123456
    assert parts["seq"] == 9
    assert parts["nonce"] == FIXED_NONCE
    assert parts["minutes"] == int((FIXED_TS - EPOCH).total_seconds() // 60) % 10000


def test_single_digit_tamper_is_rejected():
    token = build_token48("0001", "0002", 45000, 7, FIXED_NONCE, FIXED_TS)
    index = 20
    replacement = "0" if token[index] != "0" else "1"
    tampered = token[:index] + replacement + token[index + 1 :]
    ok, reason = verify_token48(tampered)
    assert ok is False
    assert reason == "E_TOKEN_CHECKSUM"


def test_short_token_is_malformed():
    ok, reason = verify_token48("123")
    assert ok is False
    assert reason == "E_MALFORMED"


def test_non_numeric_token_is_malformed():
    ok, reason = verify_token48("a" * 48)
    assert ok is False
    assert reason == "E_MALFORMED"


def test_decode_returns_none_for_bad_token():
    assert decode_token48("0" * 47) is None


def test_nonce_is_twenty_digits():
    nonce = make_nonce()
    assert len(nonce) == 20
    assert nonce.isdigit()


def test_short_hash_is_stable_and_four_digits():
    assert short_hash("device-1") == short_hash("device-1")
    assert len(short_hash("device-1")) == 4
    assert short_hash("device-1").isdigit()


def test_amount_wider_than_eight_digits_is_rejected():
    with pytest.raises(ValueError):
        build_token48("0001", "0002", 100_000_000, 1, FIXED_NONCE, FIXED_TS)


def test_seq_wraps_at_four_digits():
    token = build_token48("0001", "0002", 100, 10_001, FIXED_NONCE, FIXED_TS)
    parts = decode_token48(token)
    assert parts is not None
    assert parts["seq"] == 1
