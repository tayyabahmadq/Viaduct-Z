# seed_and_smoke.ps1 — the same end-to-end check as seed_and_smoke.sh, for Windows.
#
#   $env:BASE_URL = "https://viaduct-ledger.onrender.com"; .\deploy\seed_and_smoke.ps1
#
# Exits 0 only if every check passes.

[CmdletBinding()]
param(
    [string]$BaseUrl = $(if ($env:BASE_URL) { $env:BASE_URL } else { "http://localhost:8000" })
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

function Write-Log([string]$Message) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message) -ForegroundColor Green
}
function Write-Warn([string]$Message) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message) -ForegroundColor Yellow
}
function Fail([string]$Message) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message) -ForegroundColor Red
    exit 1
}
function Mask([string]$Value) {
    if ($Value.Length -le 10) { return $Value }
    return $Value.Substring(0, 6) + "..." + $Value.Substring($Value.Length - 4)
}
function Invoke-Json {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Bearer,
        $Body
    )
    $headers = @{}
    if ($Bearer) { $headers["Authorization"] = "Bearer $Bearer" }
    $parameters = @{
        Method      = $Method
        Uri         = "$BaseUrl$Path"
        Headers     = $headers
        ContentType = "application/json"
    }
    if ($null -ne $Body) {
        $parameters["Body"] = ($Body | ConvertTo-Json -Depth 6 -Compress)
    }
    return Invoke-RestMethod @parameters
}

# ---------------------------------------------------------------- 1. health
Write-Log "Waiting for /health (max 120s)..."
$healthy = $false
for ($attempt = 1; $attempt -le 24; $attempt++) {
    try {
        $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 5
        if ($health.status -eq "ok") { $healthy = $true; break }
    } catch {
        Start-Sleep -Seconds 5
    }
}
if (-not $healthy) {
    Fail "Timed out waiting for $BaseUrl/health (Render cold start can take 45-90s)"
}
Write-Log "/health OK"

# ------------------------------------------------------------- 2. register
Write-Log "Registering device A..."
$alice = Invoke-Json -Method Post -Path "/api/v1/devices/register" -Body @{ name = "Smoke Alice" }
Write-Log ("Device A: {0} (token: {1})" -f $alice.device_id, (Mask $alice.token48))

Write-Log "Registering device B..."
$bob = Invoke-Json -Method Post -Path "/api/v1/devices/register" -Body @{ name = "Smoke Bob" }
Write-Log ("Device B: {0} (token: {1})" -f $bob.device_id, (Mask $bob.token48))

$inside = [Math]::Floor($alice.credit_ceiling_cents / 2)
if ($inside -gt [Math]::Floor($alice.balance_cents / 2)) {
    $inside = [Math]::Floor($alice.balance_cents / 2)
}
if ($inside -lt 1) { $inside = 1 }

$above = $alice.credit_ceiling_cents + 1
if ($above -gt 10000000) {
    $above = 10000000
    if ($above -le $alice.credit_ceiling_cents) {
        Fail "This deployment's ceiling is 10,000,000 cents; no legal amount can exceed it."
    }
}

# ------------------------------------------------------- 3. inside ceiling
$key1 = "smoke-approved-$(Get-Date -UFormat %s)-$PID"
Write-Log "Payment 1: $inside cents (inside ceiling), idempotency_key=$key1"
$pay1 = Invoke-Json -Method Post -Path "/api/v1/payments" -Bearer $alice.token -Body @{
    to_token48      = $bob.token48
    amount_cents    = $inside
    idempotency_key = $key1
}
if ($pay1.status -ne "COMPLETED") {
    Fail "Payment 1 expected COMPLETED, got $($pay1.status)"
}
Write-Log "Payment 1 COMPLETED, receipt: $($pay1.transaction_id)"

# ------------------------------------------------------- 4. above ceiling
$key2 = "smoke-ceiling-$(Get-Date -UFormat %s)-$PID"
Write-Log "Payment 2: $above cents (above ceiling), idempotency_key=$key2"
$pay2 = Invoke-Json -Method Post -Path "/api/v1/payments" -Bearer $alice.token -Body @{
    to_token48      = $bob.token48
    amount_cents    = $above
    idempotency_key = $key2
}
if ($pay2.status -ne "DECLINED" -or $pay2.reason_code -ne "E_CEILING_EXCEEDED") {
    Fail "Payment 2 expected DECLINED + E_CEILING_EXCEEDED, got status=$($pay2.status) reason=$($pay2.reason_code)"
}
Write-Log "Payment 2 DECLINED with E_CEILING_EXCEEDED as expected"

# --------------------------------------------------- 5. idempotent replay
Write-Log "Payment 3: Repeat idempotency_key_1 (should return the same receipt)"
$pay3 = Invoke-Json -Method Post -Path "/api/v1/payments" -Bearer $alice.token -Body @{
    to_token48      = $bob.token48
    amount_cents    = $inside
    idempotency_key = $key1
}
if ($pay3.status -ne "COMPLETED" -or $pay3.transaction_id -ne $pay1.transaction_id) {
    Fail "Payment 3 expected COMPLETED with receipt $($pay1.transaction_id), got status=$($pay3.status) receipt=$($pay3.transaction_id)"
}
Write-Log "Payment 3 returned identical receipt: $($pay3.transaction_id)"

# ------------------------------------------------ 6. receipt token integrity
$verified = Invoke-Json -Method Post -Path "/api/v1/tokens/verify" -Bearer $alice.token -Body @{
    token48 = $pay1.token48
}
if (-not $verified.valid) {
    Fail "Receipt token failed server-side verification"
}

# ------------------------------------------------ 7. double-entry journal
$ledger = Invoke-Json -Method Get -Path "/api/v1/ledger/summary" -Bearer $alice.token
if (-not $ledger.balanced) {
    Fail "Ledger journal is not balanced: $($ledger | ConvertTo-Json -Compress)"
}
Write-Log ("Journal balanced: debit={0} credit={1} settled={2}" -f $ledger.total_debits, $ledger.total_credits, $ledger.settled_cents)

# ------------------------------------------------------------ 8. histories
if ($env:VERBOSE -eq "1") {
    Write-Log "History for device A"
    (Invoke-Json -Method Get -Path "/api/v1/payments?limit=5" -Bearer $alice.token) | ConvertTo-Json -Depth 6
    Write-Log "History for device B"
    (Invoke-Json -Method Get -Path "/api/v1/payments?limit=5" -Bearer $bob.token) | ConvertTo-Json -Depth 6
}

Write-Log "All three payments behaved exactly as specified ✓"
exit 0
