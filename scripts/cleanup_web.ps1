param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Stop-ListeningProcesses {
    param([int]$LocalPort)

    $listenPids = @()
    try {
        $listenPids = @(Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $listenPids = @(
            netstat -ano |
                Select-String ":$LocalPort" |
                ForEach-Object { ($_ -split "\s+")[-1] } |
                Where-Object { $_ -match "^\d+$" } |
                Sort-Object -Unique
        )
    }

    foreach ($processId in $listenPids) {
        if ($processId -and [int]$processId -ne $PID) {
            Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-StaleUvicornProcesses {
    $stalePids = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                ($_.CommandLine -like "*debate_agent.app.web:app*") -or
                ($_.CommandLine -like "*uvicorn*debate_agent.app.web:app*")
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    )

    foreach ($processId in $stalePids) {
        if ($processId -and [int]$processId -ne $PID) {
            Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
        }
    }
}

Stop-ListeningProcesses -LocalPort $Port
Stop-StaleUvicornProcesses
Start-Sleep -Milliseconds 500