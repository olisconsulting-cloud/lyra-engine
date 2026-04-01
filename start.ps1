# Lyra starten — PowerShell Script
# Nutzung:
#   .\start.ps1              # Normal (Terminal bleibt offen, live output)
#   .\start.ps1 -Background  # Hintergrund (eigenes Fenster, minimiert)
#   .\start.ps1 -Dashboard   # Nur Dashboard oeffnen (Lyra muss schon laufen)

param(
    [switch]$Background,
    [switch]$Dashboard
)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if ($Dashboard) {
    & "$ProjectDir\venv\Scripts\python.exe" "$ProjectDir\dashboard.py"
    exit
}

if ($Background) {
    # Startet Lyra in einem eigenen minimierten Fenster
    # Output wird in logs/ gespeichert
    $LogDir = "$ProjectDir\logs"
    if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

    $Date = Get-Date -Format "yyyy-MM-dd"
    $LogFile = "$LogDir\lyra_$Date.log"

    Start-Process -FilePath "$ProjectDir\venv\Scripts\python.exe" `
        -ArgumentList "$ProjectDir\run.py" `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Minimized `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError "$LogDir\lyra_errors_$Date.log"

    Write-Host ""
    Write-Host "  Lyra laeuft im Hintergrund!" -ForegroundColor Green
    Write-Host "  Log: $LogFile"
    Write-Host "  Dashboard: .\start.ps1 -Dashboard"
    Write-Host "  Stoppen: Get-Process python | Where-Object {`$_.Path -like '*Intelligenter*'} | Stop-Process"
    Write-Host ""
}
else {
    # Normal — im aktuellen Terminal
    & "$ProjectDir\venv\Scripts\python.exe" "$ProjectDir\run.py"
}
