. "$PSScriptRoot/Local-Common.ps1"
$lock = Enter-LocalLock
try {
    $records = @(Read-LocalRecords)
    if ($records.Count -eq 0) { throw 'No managed application processes. Run Start-Local.ps1.' }
    foreach ($record in $records) {
        $owned = Get-OwnedProcess $record
        if ($null -eq $owned) { throw "$($record.role) is stopped." }
        Write-Output "$($record.role): running (PID $($record.pid), identity verified)"
    }
    if ((@($records.role | Sort-Object) -join ',') -ne 'api,frontend,read-audit,relay,worker') { throw 'Managed service inventory is incomplete.' }
    Invoke-LocalCompose @('ps', '--all')
    & $script:LocalPython $script:LocalHelper verify
    if ($LASTEXITCODE -ne 0) { throw 'Local dependency/API verification failed.' }
    $config = Get-LocalConfiguration
    $response = Invoke-WebRequest "http://127.0.0.1:$($config.frontend_port)/login" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -ne 200) { throw 'Frontend is not ready.' }
    Write-Output 'LOCAL_SERVICES_VALIDATED (development); this is not production acceptance.'
} finally { $lock.Dispose() }
