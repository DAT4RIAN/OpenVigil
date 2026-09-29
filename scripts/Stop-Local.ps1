. "$PSScriptRoot/Local-Common.ps1"
$lock = Enter-LocalLock
try {
    $records = @(Read-LocalRecords)
    # Validate every identity before making changes; never stop by port or name.
    foreach ($record in $records) { Get-OwnedProcess $record | Out-Null }
    foreach ($record in $records) { Stop-OwnedProcess $record }
    foreach ($record in $records) {
        if ($null -ne (Get-OwnedProcess $record)) { throw "$($record.role) is still running." }
    }
    Save-LocalRecords @()
    if (Test-Path -LiteralPath (Join-Path $script:LocalFolder 'configuration.json')) {
        Invoke-LocalCompose @('stop')
        $config = Get-LocalConfiguration
        foreach ($port in @($config.frontend_port, $config.api_port) + @($config.dependency_ports)) {
            Assert-LocalPortFree $port
        }
    }
    Write-Output 'Owned local services stopped. Containers, credentials and data volumes are preserved.'
} finally { $lock.Dispose() }
