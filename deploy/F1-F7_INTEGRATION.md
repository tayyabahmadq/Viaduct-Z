# F1–F7 integration report

What was adopted from `F1-F7_extracted_for_local.zip`, what was deliberately
not, and the evidence. Branch: `full-scope`. Baseline before integration:
**84 tests green**, canonical fixtures byte-identical to
`reference/fixtures/guard_fixtures.json`.

## Decision table

| Module | Decision | Why / evidence |
|---|---|---|
| **F1** persistence | **Partially adopted**: double-entry journal, reconciliation summary, backfill, tests | F1's tree is async SQLAlchemy with `Account`/`device_id` naming and known bugs (lock swap, ceiling semantics, 56-digit token). Porting it wholesale would fight the sync server. The additive core — journal + reconciliation — was implemented against `Device`/`Payment` in `server/app/routers/ledger.py` and `server/app/backfill.py`; 8 tests in `test_ledger.py`. |
| **F2** server | **Not adopted as base** | `F2run` needed 7 boot patches, ships zero tests, and its `security.py` generated random 48-digit device tokens that fail their own checksum. The repo server already implements the same contract with 116 tests plus PayPal/AI. Replacing it would violate the no-regression law. |
| **F3** Android | **No tree swap**; deltas already present | The repo already uses Kotlin 2.0's `org.jetbrains.kotlin.plugin.compose` (no stale `kotlinCompilerExtensionVersion`), has no `timber` import, and already reads the canonical fixtures. F3's 49-file tree cannot be compiled here (no Android SDK); swapping it would trade a reviewed client for an unverifiable one. F3's TxGuard parity result (exact) is corroborated by the shared fixtures. |
| **F4** QA/CI | **Adopted after correction**: `server/tests/test_contract_qa.py` | F4's helpers expected `status: "accepted"`, a `token48` history field, 4xx declines, and integer batch counts. Corrected to `COMPLETED`, `counterparty_token48`, `200 + DECLINED + reason_code`, and list-shaped `accepted`/`declined`. Its amount-triggered `E_GUARDRAIL_BLOCKED` and quarantine tests assume rules the pinned contract does not have; quarantine is recorded as a skip with the reason. 8 tests pass, 1 skip. |
| **F5** ops | **Adopted and completed**: 5 docs under `deploy/` | F5's `cloudflared_extra.md` and `live_verification_checklist.md` were truncated mid-sentence, `neon_runbook.md` ended with a stray `</details>`, and it used `viaduct-demo` / `viaduct-db` while the live config uses `viaduct-db-env`. The docs were rewritten with correct names and complete steps. `keepalive.md` and `render.yaml` keep the repo versions (already correct). |
| **F6** on-device | **Not integrated** | The output is a blocked report from a machine without `saas-security-kit`; it must be re-dispatched on the kit laptop under LOCAL-ONLY rules. Nothing to merge. |
| **F7** data | **Adopted via replacement**: `scripts/gen_fixtures.py`, 16 appended cases | F7's generator crashed on case 1 (`"abcd"` → `int()`), used `balance_cents`/`credit_ceiling_cents` instead of the canonical `balance`/`credit_ceiling`, and emitted `{id, description, …}` instead of `{name, …}`. It was replaced with a canonical-aware, append-only generator; `--check` makes it idempotent. |

## No-regression evidence

- **Canonical fixtures untouched**: the first 30 cases are compared against the
  reference on every generator run; only 16 new names are appended (46 total).
- **Test count**: 84 → **116 passed, 1 skipped**. New coverage: 8 journal tests,
  8 contract-suite tests, 16 guard fixtures.
- **Token algorithm frozen**: no change to `server/app/tokens.py`; receipt and
  device tokens are still 44+4 with mod-97.
- **Guard parity**: both Python and Kotlin read the same 46-case file; the
  Kotlin test asserts `size >= 30` so appends are allowed but the canonical
  minimum is enforced.
- **Smoke script** still passes against a live local server after the journal
  change (payments now write two extra rows in the same transaction).

## What is still not verified

- F1's Alembic chain and Postgres-specific migration tests: not ported, because
  the demo uses `Base.metadata.create_all` and the handoff's own review found
  the migration test unable to target its temp database.
- F3 Kotlin compilation: no Android SDK on this machine; CI's `apk` job remains
  the referee.
- F2/F7 Postgres paths: SQLite only here.
- F5 dashboard steps: no Render/Neon account on this machine.

## Files touched

| Area | Files |
|---|---|
| Journal | `server/app/models.py`, `server/app/routers/payments.py`, `server/app/routers/ledger.py`, `server/app/backfill.py`, `server/app/schemas.py`, `server/app/main.py`, `server/tests/test_ledger.py` |
| Fixtures | `fixtures/guard_fixtures.json`, `scripts/gen_fixtures.py`, `server/tests/test_guard.py`, `android/.../TxGuardTest.kt` |
| QA | `server/tests/test_contract_qa.py` |
| Ops | `deploy/neon_runbook.md`, `deploy/backups_rollback.md`, `deploy/clickpath_runbook.md`, `deploy/live_verification_checklist.md`, `deploy/cloudflared_extra.md` |
