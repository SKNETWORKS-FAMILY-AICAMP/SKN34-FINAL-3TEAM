$ErrorActionPreference='Stop'
$trialRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:CORE_HOST_PORT='18095'
$env:CORE_PROXY_TARGET='http://127.0.0.1:18095'
$env:CORE_PROXY_HOST=''
$env:TRANSFER_GOOGLE_PROXY_TARGET='http://127.0.0.1:18096'
$env:VITE_API_MOCK='false'
$env:VITE_GUARDIAN_TRANSFER_ENABLED='true'
Push-Location (Join-Path $trialRoot 'frontend/web')
try { & npm run dev -- --host 127.0.0.1 --port 5195 --strictPort } finally { Pop-Location }
