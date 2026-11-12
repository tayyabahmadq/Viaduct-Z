# Starts the Viaduct Pay mobile simulation (API + phone UI).
# Ctrl+C stops both. Re-run this file to start it again.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Prefer the system Node: its inbound firewall rule is already in place on this PC,
# so the phone can reach the server without touching Windows Firewall.
$candidates = @(
    'C:\Program Files\nodejs\node.exe',
    'C:\Program Files (x86)\nodejs\node.exe'
)
$node = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $node) {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { $node = $cmd.Source }
}
if (-not $node) {
    Write-Host 'Node.js 22+ is required to run the simulator.' -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host "  Viaduct Pay - mobile simulation" -ForegroundColor Cyan
Write-Host "  node: $node" -ForegroundColor DarkGray
Write-Host ''

& $node (Join-Path $here 'serve.js')
