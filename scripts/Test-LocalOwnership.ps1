. "$PSScriptRoot/Local-Common.ps1"
[IO.Directory]::CreateDirectory($script:LocalFolder) | Out-Null
$sentinelFile = Join-Path $script:LocalFolder "ownership-sentinel-$([guid]::NewGuid().ToString('N')).ps1"
Set-Content -LiteralPath $sentinelFile -Value 'Start-Sleep -Seconds 120'
$record = $null
try {
    $shell = (Get-Process -Id $PID).Path
    $record = Start-OwnedProcess 'ownership-test' $shell @('-NoProfile', '-File', $sentinelFile)
    if ($null -eq (Get-OwnedProcess $record)) { throw 'Sentinel was not started.' }
    $roundTrip = $record | ConvertTo-Json | ConvertFrom-Json
    if ($null -eq (Get-OwnedProcess $roundTrip)) { throw 'Serialized identity cannot be revalidated.' }
    $originalCreation = $record.created
    $record.created = 'wrong-creation-time'
    $rejected = $false
    try { Stop-OwnedProcess $record } catch { $rejected = $true }
    if (-not $rejected) { throw 'Mismatched PID identity was accepted.' }
    $record.created = $originalCreation
    if ($null -eq (Get-OwnedProcess $record)) { throw 'Identity rejection killed the sentinel.' }
    Stop-OwnedProcess $record
    if ($null -ne (Get-OwnedProcess $record)) { throw 'Owned sentinel was not stopped.' }
    Stop-OwnedProcess $record
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        $port = $listener.LocalEndpoint.Port
        $rejected = $false
        try { Assert-LocalPortFree $port } catch { $rejected = $true }
        if (-not $rejected) { throw 'Occupied port was accepted.' }
        if (-not $listener.Server.IsBound) { throw 'Preflight affected another port owner.' }
    } finally { $listener.Stop() }
    Write-Output 'PASS: recycled PID rejected; unrelated process preserved; owned stop idempotent; occupied port preserved.'
} finally {
    if ($null -ne $record) { Stop-OwnedProcess $record }
    Remove-Item -LiteralPath $sentinelFile
}
