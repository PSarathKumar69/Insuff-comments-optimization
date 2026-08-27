# Local dev server for the Education Dropdown MVP.
#
# Run this rather than typing `php -S` by hand. The `router.php` argument is
# NOT optional: it maps /api/*.php to ../api/, matching the URLs Vercel serves
# (see router.php and vercel.json). Started without it, PHP's built-in server
# answers /api/data.php with index.html and HTTP 200, and every dropdown on the
# page stays empty - that exact mistake cost three debugging rounds on
# 2026-08-27, which is why this script exists and why it kills stale servers
# below: reloading the browser does nothing if the old server is still up.

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

# 1. Is PHP even reachable?
$php = Get-Command php -ErrorAction SilentlyContinue
if ($null -eq $php) {
    Write-Host "php not found on PATH. Install PHP 8.x and reopen the terminal." -ForegroundColor Red
    exit 1
}

# 2. Kill any server already holding port 8000 - almost always a previous run of
#    this app, possibly started with the wrong arguments. Without this, a stale
#    process keeps answering and every fix looks like it did nothing.
$stale = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $stale) {
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($null -ne $proc) {
        Write-Host "Stopping stale server on port 8000: $($proc.ProcessName) (PID $($proc.Id))" -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 400
    }
}

# 3. Sanity-check the layout, so a wrong working directory fails clearly here
#    instead of as blank dropdowns in the browser.
foreach ($required in @('public\index.html', 'router.php', 'api\data.php', 'data\templates.json')) {
    if (-not (Test-Path $required)) {
        Write-Host "Missing $required - run this from the Education_Dropdown_MVP folder." -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path 'data\search_index.json')) {
    Write-Host "Note: data\search_index.json is absent, so the support-triage search card will report 'Search unavailable'. The comment generator works normally. See README.md." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "Serving http://localhost:8000  (Ctrl+C to stop)" -ForegroundColor Green
Write-Host "If dropdowns are empty, hard-reload the page with Ctrl+F5." -ForegroundColor DarkGray
Write-Host ""

php -S localhost:8000 -t public router.php
