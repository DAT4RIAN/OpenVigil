Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:LocalRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script:LocalFolder = Join-Path $script:LocalRoot '.artifacts/local-stack'
$script:LocalStatePath = Join-Path $script:LocalFolder 'processes.json'
$script:LocalPython = Join-Path $script:LocalRoot 'backend/.venv/Scripts/python.exe'
$script:LocalHelper = Join-Path $PSScriptRoot 'local_backend.py'

function Enter-LocalLock {
    [IO.Directory]::CreateDirectory($script:LocalFolder) | Out-Null
    # The operating system releases the exclusive handle after crashes.
    return [IO.File]::Open((Join-Path $script:LocalFolder 'manager.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
}

function Read-LocalRecords {
    if (-not (Test-Path -LiteralPath $script:LocalStatePath)) { return @() }
    $state = Get-Content -LiteralPath $script:LocalStatePath -Raw | ConvertFrom-Json
    if ($state.root -ne $script:LocalRoot) { throw 'Process state belongs to another checkout.' }
    return @($state.processes)
}

function Save-LocalRecords([object[]]$Records) {
    $temp = "$script:LocalStatePath.tmp"
    @{ root = $script:LocalRoot; processes = @($Records) } | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $temp -Encoding utf8
    Move-Item -LiteralPath $temp -Destination $script:LocalStatePath -Force
}

function Get-OwnedProcess($Record) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$Record.pid)"
    if ($null -eq $process) { return $null }
    $created = $process.CreationDate.ToUniversalTime().Ticks
    # PowerShell 7 can deserialize ISO JSON dates as DateTime; compare instants,
    # not culture-dependent string conversions after a manager restart.
    if ($created -ne ([DateTimeOffset]$Record.created).UtcDateTime.Ticks -or $process.CommandLine -ne $Record.command -or
        $process.ExecutablePath -ne $Record.executable -or
        -not $process.CommandLine.Contains($script:LocalRoot)) {
        throw "Refusing process $($Record.pid): PID identity or checkout ownership differs."
    }
    return $process
}

function Stop-OwnedProcess($Record) {
    $parent = Get-OwnedProcess $Record
    if ($null -eq $parent) { return }
    # Discover only descendants of the verified root. Recheck each creation time
    # immediately before stopping it to protect against recycled process IDs.
    $tree = [Collections.Generic.List[object]]::new()
    $tree.Add($parent)
    for ($index = 0; $index -lt $tree.Count; $index++) {
        $item = $tree[$index]
        foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($item.ProcessId)")) {
            if ($child.CreationDate -ge $item.CreationDate) { $tree.Add($child) }
        }
    }
    for ($index = $tree.Count - 1; $index -ge 0; $index--) {
        $item = $tree[$index]
        $live = Get-CimInstance Win32_Process -Filter "ProcessId = $($item.ProcessId)"
        if ($null -ne $live -and $live.CreationDate -eq $item.CreationDate -and
            $live.CommandLine -eq $item.CommandLine) {
            Stop-Process -Id $live.ProcessId -Force -ErrorAction Stop
        }
    }
}

function Start-OwnedProcess([string]$Role, [string]$Executable, [string[]]$Arguments) {
    # Windows command-line quoting; these arguments never pass through a shell.
    $quoted = @($Arguments | ForEach-Object {
        if ($_ -match '["\r\n]') { throw 'Unexpected quote or newline in process argument.' }
        '"' + $_ + '"'
    })
    $process = Start-Process -FilePath $Executable -ArgumentList $quoted -WorkingDirectory $script:LocalRoot `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $script:LocalFolder "$Role.stdout.log") `
        -RedirectStandardError (Join-Path $script:LocalFolder "$Role.stderr.log")
    $observed = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
    if ($null -eq $observed) { throw "$Role exited immediately; inspect its private log." }
    return [PSCustomObject]@{
        role = $Role; pid = $observed.ProcessId
        created = $observed.CreationDate.ToUniversalTime().ToString('o')
        command = $observed.CommandLine; executable = $observed.ExecutablePath
    }
}

function Get-LocalConfiguration {
    $config = Get-Content -LiteralPath (Join-Path $script:LocalFolder 'configuration.json') -Raw | ConvertFrom-Json
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($script:LocalRoot))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($config.root -ne $script:LocalRoot -or $config.project -ne "openvigil-dev-$($hash.Substring(0, 10))") {
        throw 'Compose project ownership does not match this checkout.'
    }
    return $config
}

function Invoke-LocalCompose([string[]]$ComposeArguments) {
    $config = Get-LocalConfiguration
    & docker compose --project-name $config.project -f (Join-Path $script:LocalFolder 'compose.json') `
        --env-file (Join-Path $script:LocalFolder '.env.runtime') @ComposeArguments
    if ($LASTEXITCODE -ne 0) { throw "Local Compose operation failed (exit $LASTEXITCODE)." }
}

function Assert-LocalPortFree([int]$Port) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() }
    catch { throw "Port $Port is already occupied. Its owner will not be stopped." }
    finally { $listener.Stop() }
}
