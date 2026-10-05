param([switch]$Postgres)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run python -m venv .venv and install requirements.txt first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules'))) { throw 'Run npm install in frontend first.' }
New-Item -ItemType Directory -Path (Join-Path $projectRoot 'output') -Force | Out-Null
$apiReady = $false
$webReady = $false
try {
  $runningApi = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2
  $apiReady = $runningApi.name -eq 'ResQ Kerala API'
} catch { }
try {
  $runningWeb = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -TimeoutSec 2 -UseBasicParsing
  $webReady = $runningWeb.Content -match '<title>ResQ Kerala'
} catch { }
if ($apiReady -and $webReady) { Write-Output 'ResQ Kerala is already running: http://localhost:5173'; return }
if (-not $apiReady -and $Postgres) {
  docker compose up -d db
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL could not start.' }
  $env:DATABASE_URL = 'postgresql+psycopg://resq:resq-local-demo-password@127.0.0.1:5433/resq'
}
elseif (-not $apiReady -and (Test-Path -LiteralPath (Join-Path $projectRoot 'output\postgres\pgsql\bin\pg_ctl.exe'))) {
  $pgControl = Join-Path $projectRoot 'output\postgres\pgsql\bin\pg_ctl.exe'
  $pgData = Join-Path $projectRoot 'output\postgres\pgdata'
  & $pgControl -D $pgData status | Out-Null
  if ($LASTEXITCODE -ne 0) {
    & $pgControl -D $pgData -l (Join-Path $projectRoot 'output\postgres\server.log') -o '-p 5433 -h 127.0.0.1' start
    if ($LASTEXITCODE -ne 0) { throw 'Project-local PostgreSQL could not start.' }
  }
}
$processRecord = @{}
$pidFile = Join-Path $projectRoot 'output\processes.json'
if (Test-Path -LiteralPath $pidFile) {
  $previous = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
  foreach ($property in $previous.PSObject.Properties) { $processRecord[$property.Name] = $property.Value }
}
if (-not $apiReady) {
  $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'output\backend.log') -RedirectStandardError (Join-Path $projectRoot 'output\backend-error.log')
  $processRecord.api = $apiProcess.Id
  $processRecord.api_started = $apiProcess.StartTime.ToUniversalTime().ToString('o')
}
if (-not $webReady) {
  $npmCommand = (Get-Command npm.cmd).Source
  $webProcess = Start-Process -FilePath $npmCommand -ArgumentList @('run','dev') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'output\frontend.log') -RedirectStandardError (Join-Path $projectRoot 'output\frontend-error.log')
  $processRecord.frontend = $webProcess.Id
  $processRecord.frontend_started = $webProcess.StartTime.ToUniversalTime().ToString('o')
}
$processRecord | ConvertTo-Json | Set-Content -LiteralPath $pidFile
Write-Output 'ResQ Kerala: http://localhost:5173 | API docs: http://localhost:8000/docs'
