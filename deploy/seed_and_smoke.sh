#!/usr/bin/env bash
# End-to-end smoke test for the Viaduct Pay ledger.
#
#   BASE_URL=https://viaduct-ledger.onrender.com ./deploy/seed_and_smoke.sh
#
# Verifies, against a live server:
#   1. /health answers
#   2. two devices can register
#   3. a payment inside the ceiling settles
#   4. a payment above the ceiling is declined with E_CEILING_EXCEEDED
#   5. replaying the same idempotency key returns the identical receipt
#
# Exits 0 only if every check passes. Needs curl and Python 3 (no jq).

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
NC=$'\033[0m'

log()  { printf '%s[%s]%s %s\n' "$GREEN"  "$(date -u +%H:%M:%S)" "$NC" "$*"; }
warn() { printf '%s[%s]%s %s\n' "$YELLOW" "$(date -u +%H:%M:%S)" "$NC" "$*"; }
err()  { printf '%s[%s]%s %s\n' "$RED"    "$(date -u +%H:%M:%S)" "$NC" "$*" >&2; }

# json <dotted.path> — read a value from stdin without depending on jq.
json() {
  "$PYTHON" -c 'import json, sys
data = json.load(sys.stdin)
for key in sys.argv[1].split("."):
    data = data[key]
print(data)' "$1"
}

mask() {
  local value="$1"
  printf '%s…%s' "${value:0:6}" "${value: -4}"
}

# ---------------------------------------------------------------- 1. health
log "Waiting for /health (max 120s)..."
for attempt in $(seq 1 24); do
  if curl -fsS --max-time 5 "$BASE_URL/health" >/dev/null 2>&1; then
    log "/health OK"
    break
  fi
  if [ "$attempt" -eq 24 ]; then
    err "Timed out waiting for $BASE_URL/health"
    err "Render free tier cold starts take 45–90 s; re-run once the service is awake."
    exit 1
  fi
  sleep 5
done

# ------------------------------------------------------------- 2. register
log "Registering device A..."
REG_A=$(curl -fsS -X POST "$BASE_URL/api/v1/devices/register" \
  -H 'content-type: application/json' -d '{"name":"Smoke Alice"}')
DEVICE_A=$(printf '%s' "$REG_A" | json device_id)
BEARER_A=$(printf '%s' "$REG_A" | json token)
TOKEN48_A=$(printf '%s' "$REG_A" | json token48)
BALANCE_A=$(printf '%s' "$REG_A" | json balance_cents)
CEILING_A=$(printf '%s' "$REG_A" | json credit_ceiling_cents)
log "Device A: $DEVICE_A (token: $(mask "$TOKEN48_A"))"

log "Registering device B..."
REG_B=$(curl -fsS -X POST "$BASE_URL/api/v1/devices/register" \
  -H 'content-type: application/json' -d '{"name":"Smoke Bob"}')
DEVICE_B=$(printf '%s' "$REG_B" | json device_id)
BEARER_B=$(printf '%s' "$REG_B" | json token)
TOKEN48_B=$(printf '%s' "$REG_B" | json token48)
log "Device B: $DEVICE_B (token: $(mask "$TOKEN48_B"))"

# Pick an amount that definitely fits both the ceiling and half the balance,
# and one that certainly exceeds the ceiling, whatever the deployment config is.
INSIDE=$(( CEILING_A / 2 ))
if [ "$INSIDE" -gt "$(( BALANCE_A / 2 ))" ]; then INSIDE=$(( BALANCE_A / 2 )); fi
if [ "$INSIDE" -lt 1 ]; then INSIDE=1; fi

ABOVE=$(( CEILING_A + 1 ))
if [ "$ABOVE" -gt 10000000 ]; then
  ABOVE=10000000
  if [ "$ABOVE" -le "$CEILING_A" ]; then
    err "This deployment's ceiling is 10,000,000 cents; no legal amount can exceed it."
    exit 1
  fi
fi

pay() { # pay <bearer> <json-body>
  curl -fsS -X POST "$BASE_URL/api/v1/payments" \
    -H "authorization: Bearer $1" -H 'content-type: application/json' -d "$2"
}

# ------------------------------------------------------- 3. inside ceiling
KEY1="smoke-approved-$(date +%s)-$$"
log "Payment 1: $INSIDE cents (inside ceiling), idempotency_key=$KEY1"
PAY1=$(pay "$BEARER_A" "{\"to_token48\":\"$TOKEN48_B\",\"amount_cents\":$INSIDE,\"idempotency_key\":\"$KEY1\"}")
STATUS1=$(printf '%s' "$PAY1" | json status)
RECEIPT1=$(printf '%s' "$PAY1" | json transaction_id)
if [ "$STATUS1" != "COMPLETED" ]; then
  err "Payment 1 expected COMPLETED, got $STATUS1"
  printf '%s\n' "$PAY1" >&2
  exit 1
fi
log "Payment 1 COMPLETED, receipt: $RECEIPT1"

# ------------------------------------------------------- 4. above ceiling
KEY2="smoke-ceiling-$(date +%s)-$$"
log "Payment 2: $ABOVE cents (above ceiling), idempotency_key=$KEY2"
PAY2=$(pay "$BEARER_A" "{\"to_token48\":\"$TOKEN48_B\",\"amount_cents\":$ABOVE,\"idempotency_key\":\"$KEY2\"}")
STATUS2=$(printf '%s' "$PAY2" | json status)
REASON2=$(printf '%s' "$PAY2" | json reason_code)
if [ "$STATUS2" != "DECLINED" ] || [ "$REASON2" != "E_CEILING_EXCEEDED" ]; then
  err "Payment 2 expected DECLINED + E_CEILING_EXCEEDED, got status=$STATUS2 reason=$REASON2"
  printf '%s\n' "$PAY2" >&2
  exit 1
fi
log "Payment 2 DECLINED with E_CEILING_EXCEEDED as expected"

# --------------------------------------------------- 5. idempotent replay
log "Payment 3: Repeat idempotency_key_1 (should return the same receipt)"
PAY3=$(pay "$BEARER_A" "{\"to_token48\":\"$TOKEN48_B\",\"amount_cents\":$INSIDE,\"idempotency_key\":\"$KEY1\"}")
STATUS3=$(printf '%s' "$PAY3" | json status)
RECEIPT3=$(printf '%s' "$PAY3" | json transaction_id)
if [ "$STATUS3" != "COMPLETED" ] || [ "$RECEIPT3" != "$RECEIPT1" ]; then
  err "Payment 3 expected COMPLETED with receipt $RECEIPT1, got status=$STATUS3 receipt=$RECEIPT3"
  printf '%s\n' "$PAY3" >&2
  exit 1
fi
log "Payment 3 returned identical receipt: $RECEIPT3"

# ------------------------------------------------ 6. receipt token integrity
TOKEN48_RECEIPT=$(printf '%s' "$PAY1" | json token48)
VERIFIED=$(curl -fsS -X POST "$BASE_URL/api/v1/tokens/verify" \
  -H "authorization: Bearer $BEARER_A" -H 'content-type: application/json' \
  -d "{\"token48\":\"$TOKEN48_RECEIPT\"}")
if [ "$(printf '%s' "$VERIFIED" | json valid)" != "True" ]; then
  err "Receipt token failed server-side verification"
  printf '%s\n' "$VERIFIED" >&2
  exit 1
fi

# ------------------------------------------------------------ 7. histories
if [ "${VERBOSE:-0}" = "1" ]; then
  log "History for device A"
  curl -fsS "$BASE_URL/api/v1/payments?limit=5" -H "authorization: Bearer $BEARER_A" | "$PYTHON" -m json.tool
  log "History for device B"
  curl -fsS "$BASE_URL/api/v1/payments?limit=5" -H "authorization: Bearer $BEARER_B" | "$PYTHON" -m json.tool
fi

log "All three payments behaved exactly as specified ✓"
exit 0
