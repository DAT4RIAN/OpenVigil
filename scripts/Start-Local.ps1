param(
    [ValidateRange(1024, 65535)][int]$FrontendPort = 3000,
    [ValidateRange(1024, 65535)][int]$ApiPort = 8000
)
. "$PSScriptRoot/Local-Common.ps1"
$lock = Enter-LocalLock
$started = [Collections.Generic.List[object]]::new()
$records = @()
try {
    if (-not (Test-Path -LiteralPath $script:LocalPython)) { throw 'Install backend/.venv with the README instructions first.' }
    $node = (Get-Command node -CommandType Application | Select-Object -First 1).Source
    & docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is unavailable. Start Docker Desktop, then rerun.' }
    $records = @(Read-LocalRecords)
    foreach ($record in $records) { Get-OwnedProcess $record | Out-Null }
    if (Test-Path -LiteralPath (Join-Path $script:LocalFolder 'configuration.json')) {
        $saved = Get-LocalConfiguration
        if (-not $PSBoundParameters.ContainsKey('FrontendPort')) { $FrontendPort = $saved.frontend_port }
        if (-not $PSBoundParameters.ContainsKey('ApiPort')) { $ApiPort = $saved.api_port }
    }
    & $script:LocalPython $script:LocalHelper prepare --frontend-port $FrontendPort --api-port $ApiPort
    if ($LASTEXITCODE -ne 0) { throw 'Local configuration validation failed.' }
    # Do not migrate beneath live application processes during an idempotent restart.
    $live = @($records | Where-Object { $null -ne (Get-OwnedProcess $_) })
    if ($live.Count -gt 0) {
        if ($live.Count -eq 5 -and (@($live.role | Sort-Object) -join ',') -eq 'api,frontend,read-audit,relay,worker') {
            & $script:LocalPython $script:LocalHelper verify
            if ($LASTEXITCODE -ne 0) { throw 'Existing stack is not ready; inspect Status-Local.ps1 and private logs.' }
            $response = Invoke-WebRequest "http://127.0.0.1:$FrontendPort/login" -TimeoutSec 5 -UseBasicParsing
            if ($response.StatusCode -ne 200) { throw 'Existing frontend is not ready.' }
            Write-Output 'Existing managed stack is ready; no services or data were replaced.'
            return
        }
        throw 'A partial managed stack is still running. Run Stop-Local.ps1 before restarting.'
    }
    Assert-LocalPortFree $FrontendPort
    Assert-LocalPortFree $ApiPort
    # Compose validates dependency bindings; it never replaces unrelated port owners.
    Invoke-LocalCompose @('up', '-d', '--wait', '--wait-timeout', '180', 'postgres', 'redis', 'minio', 'neo4j')
    Invoke-LocalCompose @('run', '--rm', '--no-deps', 'minio-init')
    & $script:LocalPython $script:LocalHelper migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; application processes were not started.' }
    Push-Location $script:LocalRoot
    try {
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    $records = @()
    foreach ($role in @('relay', 'worker', 'read-audit', 'api')) {
        $record = Start-OwnedProcess $role $script:LocalPython @($script:LocalHelper, $role)
        $started.Add($record)
        $records += $record
        Save-LocalRecords $records
    }
    # Pin Demo mode for this development stack; root dotenv cannot silently switch
    # the frontend to an unrelated production endpoint.
    $oldMode = $env:WINDOPS_RUNTIME_MODE
    try {
        $env:WINDOPS_RUNTIME_MODE = 'demo'
        $record = Start-OwnedProcess 'frontend' $node @((Join-Path $PSScriptRoot 'run-vinext.mjs'), 'start', '--port', "$FrontendPort")
        $started.Add($record)
        $records += $record
        Save-LocalRecords $records
    } finally { $env:WINDOPS_RUNTIME_MODE = $oldMode }
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        foreach ($record in $records) {
            if ($null -eq (Get-OwnedProcess $record)) { throw "$($record.role) exited; inspect private logs." }
        }
        try {
            $api = Invoke-WebRequest "http://127.0.0.1:$ApiPort/api/v1/healthz" -TimeoutSec 2 -UseBasicParsing
            $ui = Invoke-WebRequest "http://127.0.0.1:$FrontendPort/login" -TimeoutSec 2 -UseBasicParsing
            if ($api.StatusCode -eq 200 -and $ui.StatusCode -eq 200) { $ready = $true; break }
        } catch { Write-Verbose "Waiting for API/frontend readiness (attempt $attempt)." }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Local readiness deadline exceeded.' }
    & $script:LocalPython $script:LocalHelper verify
    if ($LASTEXITCODE -ne 0) { throw 'Dependency/auth/read-audit verification failed.' }
    Write-Output "Development stack ready: http://127.0.0.1:$FrontendPort/login ; API http://127.0.0.1:$ApiPort"
    Write-Output 'Frontend uses Demo data. Independent Python services are verified locally; production gateway acceptance remains separate.'
} catch {
    foreach ($record in $started) { Stop-OwnedProcess $record }
    if ($started.Count -gt 0) { Save-LocalRecords @() }
    # Retain dependencies and volumes for diagnosis and a safe rerun.
    throw
} finally { $lock.Dispose() }
