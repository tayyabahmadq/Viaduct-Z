package com.viaduct.pay.utils

import kotlinx.serialization.Serializable
import java.math.BigInteger

/**
 * Client-side mirror of `server/app/guard.py::screen`.
 *
 * Both implementations are checked against `fixtures/guard_fixtures.json`, so a
 * rule change must be made in both places or the shared fixtures fail.
 *
 * This is an advisory pre-check: the server's `db_guard` is authoritative.
 */

@Serializable
data class TxDraft(
    val sender_account_id: String?,
    // Nullable to mirror guard.screen(): the canonical fixture
    // "malformed beats self payment" carries a null receiver, and the
    // malformed rule fires on the null sender before the receiver is read.
    val receiver_account_id: String?,
    val amount: Int,
    val nonce: String,
    val token48: String? = null,
    val timestamp_ms: Long
)

@Serializable
data class AccountState(
    val account_id: String,
    val balance: Int,
    val credit_ceiling: Int,
    val seq: Int,
    val recent_timestamps_ms: List<Long> = emptyList(),
    val seen_nonces: Set<String> = emptySet(),
    val blacklist: Set<String> = emptySet()
)

@Serializable
data class GuardDecision(
    val decision: String,
    val code: String,
    val reason: String,
    val score: Int
)

object TxGuard {
    private const val VELOCITY_WINDOW_MS = 60_000L
    private const val VELOCITY_LIMIT = 5

    fun screen(tx: TxDraft, state: AccountState): GuardDecision {
        val sender = tx.sender_account_id
        val receiver = tx.receiver_account_id
        val token = tx.token48

        // R0 — malformed input.
        if (sender == null ||
            tx.amount < 0 ||
            (token != null && (token.length != 48 || !token.all { it.isDigit() }))
        ) {
            return GuardDecision("DENY", "E_MALFORMED", "Malformed input", 100)
        }

        // R1 — self payment.
        if (tx.receiver_account_id == sender) {
            return GuardDecision("DENY", "E_SELF_PAY", "Self payment", 10)
        }

        // R2 — quarantined recipient.
        if (receiver != null && state.blacklist.contains(receiver)) {
            return GuardDecision("DENY", "E_QUARANTINED_PEER", "Receiver blacklisted", 100)
        }

        // R3 — receipt-token checksum.
        if (token != null) {
            val payload = token.substring(0, 44)
            val received = token.substring(44, 48)
            val computed = BigInteger(payload)
                .mod(BigInteger.valueOf(97))
                .toString()
                .padStart(4, '0')
            if (computed != received) {
                return GuardDecision("DENY", "E_GUARDRAIL_BLOCKED", "checksum", 45)
            }
        }

        // R4 — nonce replay.
        if (state.seen_nonces.contains(tx.nonce)) {
            return GuardDecision("DENY", "E_DUPLICATE_TOKEN", "Duplicate nonce", 45)
        }

        // R5 — velocity.
        val threshold = tx.timestamp_ms - VELOCITY_WINDOW_MS
        if (state.recent_timestamps_ms.count { it >= threshold } >= VELOCITY_LIMIT) {
            return GuardDecision("DENY", "E_GUARDRAIL_BLOCKED", "velocity", 25)
        }

        // R6 — credit ceiling.
        if (tx.amount > state.credit_ceiling) {
            return GuardDecision("DENY", "E_CEILING_EXCEEDED", "Exceeds credit ceiling", 100)
        }

        // R7 — balance.
        if (tx.amount > state.balance) {
            return GuardDecision("DENY", "E_INSUFFICIENT_BALANCE", "Insufficient balance", 45)
        }

        return GuardDecision("ALLOW", "OK", "", 0)
    }
}
