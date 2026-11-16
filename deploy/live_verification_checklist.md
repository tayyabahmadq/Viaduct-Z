# Live verification checklist

Adapted from F5, which shipped this file truncated after "Command:". Run every
item against the deployed service and paste the real output into
`deploy/evidence_log.md`.

```powershell
$env:BASE_URL = "https://viaduct-ledger.onrender.com"
```

## 1. Health

```powershell
Invoke-RestMethod "$env:BASE_URL/health"
```

Expect `status = ok` and `service = viaduct-ledger`.

## 2. Register a wallet

```powershell
$alice = Invoke-RestMethod -Method Post "$env:BASE_URL/api/v1/devices/register" `
  -ContentType application/json -Body '{"name":"Check Alice"}'
$alice.token48.Length   # 48
```

## 3. Token checksum

```powershell
$body = @{ token48 = $alice.token48 } | ConvertTo-Json
Invoke-RestMethod -Method Post "$env:BASE_URL/api/v1/tokens/verify" `
  -Headers @{ Authorization = "Bearer $($alice.token)" } `
  -ContentType application/json -Body $body
```

Expect `valid = True`, `reason = OK`.

## 4. Payment and receipt

```powershell
$bob = Invoke-RestMethod -Method Post "$env:BASE_URL/api/v1/devices/register" `
  -ContentType application/json -Body '{"name":"Check Bob"}'
$pay = @{ to_token48 = $bob.token48; amount_cents = 2500; idempotency_key = "check-1" } | ConvertTo-Json
$receipt = Invoke-RestMethod -Method Post "$env:BASE_URL/api/v1/payments" `
  -Headers @{ Authorization = "Bearer $($alice.token)" } `
  -ContentType application/json -Body $pay
$receipt.status          # COMPLETED
$receipt.token48.Length  # 48
```

## 5. Ceiling decline

Repeat with `amount_cents = 500001` (or `credit_ceiling_cents + 1`) and a fresh
key. Expect HTTP 200, `status = DECLINED`, `reason_code = E_CEILING_EXCEEDED`.

## 6. Idempotent replay

Repeat the step-4 request with the **same** `idempotency_key`. Expect an
identical `transaction_id` and no balance change.

## 7. Journal reconciliation

```powershell
Invoke-RestMethod "$env:BASE_URL/api/v1/ledger/summary" `
  -Headers @{ Authorization = "Bearer $($alice.token)" }
```

Expect `balanced = True`, `missing_entries = 0`.

## 8. PayPal fail-closed (when unconfigured)

```powershell
try {
  Invoke-RestMethod -Method Post "$env:BASE_URL/api/v1/topups/paypal/order" `
    -Headers @{ Authorization = "Bearer $($alice.token)" } `
    -ContentType application/json -Body '{"amount_cents":2500}'
} catch { $_.Exception.Response.StatusCode.value__ }   # 503 when not configured
```

With sandbox credentials set, expect an `order_id` and an `approve_url` on
`paypal.com` instead.

## 9. AI assistant

```powershell
Invoke-RestMethod -Method Post "$env:BASE_URL/api/v1/assistant/parse" `
  -Headers @{ Authorization = "Bearer $($alice.token)" } `
  -ContentType application/json -Body '{"text":"send $25 to Aarav Shah"}'
```

Expect `action = PAY`, `amount_cents = 2500`, and `source = rules` or `model`
depending on `AI_API_KEY`.

## 10. Record the evidence

Write the command, the status code and the key response fields into
`deploy/evidence_log.md`. A claim without a captured output is not evidence.
