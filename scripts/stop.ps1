$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'output\processes.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No project process record found.'; return }
$record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$allProcesses = Get-CimInstance Win32_Process
foreach ($service in @('api','frontend')) {
  $serviceId = $record.$service
  if (-not $serviceId) { continue }
  $started = $record."${service}_started"
  $rootProcess = Get-Process -Id $serviceId -ErrorAction SilentlyContinue
  if (-not $rootProcess) { continue }
  $identityMatches = $false
  if ($started) {
    try {
      # PowerShell versions differ in whether JSON ISO timestamps become strings
      # or DateTime objects. Compare the actual UTC instant in either case.
      $identityMatches = $rootProcess.StartTime.ToUniversalTime().Ticks -eq ([datetime]$started).ToUniversalTime().Ticks
    } catch { }
  }
  if (-not $identityMatches) {
    Write-Output "Skipping $service because its process identity could not be verified."
    continue
  }
  $serviceChildren = @($serviceId)
  for ($level=0; $level -lt 5; $level++) {
    $found = @($allProcesses | Where-Object { $_.ParentProcessId -in $serviceChildren -and $_.ProcessId -notin $serviceChildren } | Select-Object -ExpandProperty ProcessId)
    if (-not $found) { break }
    $serviceChildren += $found
  }
  [array]::Reverse($serviceChildren)
  foreach ($childId in $serviceChildren) { Stop-Process -Id $childId -ErrorAction SilentlyContinue }
  Write-Output "Stopped the recorded $service process and its children."
}
Write-Output 'PostgreSQL and Ollama remain available.'
