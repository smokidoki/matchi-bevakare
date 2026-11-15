# Installerar MATCHi-bevakaren på Windows och kör den var 5:e minut.
# Kör i PowerShell:  powershell -ExecutionPolicy Bypass -File installera_windows.ps1 matchi-tennis-DITTÄMNE
param([Parameter(Mandatory=$true)][string]$Topic)
$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  Write-Host "Installera Python 3 först: https://www.python.org/downloads/ (kryssa i 'Add to PATH')"; exit 1 }
py -3 -m venv "$Dir\.venv"
& "$Dir\.venv\Scripts\pip.exe" install -q -r "$Dir\requirements.txt"
$env:NTFY_TOPIC = $Topic
& "$Dir\.venv\Scripts\python.exe" "$Dir\matchi_bevakare.py" --test-notis
[Environment]::SetEnvironmentVariable("NTFY_TOPIC", $Topic, "User")
$Action  = New-ScheduledTaskAction -Execute "$Dir\.venv\Scripts\pythonw.exe" -Argument "`"$Dir\matchi_bevakare.py`"" -WorkingDirectory $Dir
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "MATCHi-bevakare" -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "Klart! Bevakaren kör var 5:e minut (Schemaläggaren -> 'MATCHi-bevakare')."
Write-Host "Stänga av:  Unregister-ScheduledTask -TaskName MATCHi-bevakare"
