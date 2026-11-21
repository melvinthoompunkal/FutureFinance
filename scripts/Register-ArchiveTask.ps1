[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Python) {
    $projectPython = Join-Path $project '.venv/Scripts/python.exe'
    $Python = if (Test-Path -LiteralPath $projectPython) { $projectPython } else { (Get-Command python.exe).Source }
}
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$pythonw = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (Test-Path -LiteralPath $pythonw -PathType Leaf) {
    $taskExecutable = $pythonw
} else {
    $taskExecutable = $pythonPath
}

$name = 'FutureFinance Archive'
if ($PSCmdlet.ShouldProcess($name, 'Register recurring archive capture for the current user')) {
    Push-Location $project
    try {
        & $pythonPath -c 'import future_finance.collect'
        if ($LASTEXITCODE -ne 0) {
            throw 'Install the project requirements with the selected Python interpreter first.'
        }
    } finally {
        Pop-Location
    }

    $action = New-ScheduledTaskAction -Execute $taskExecutable -Argument '-m future_finance.collect tick' -WorkingDirectory $project
    $now = Get-Date
    $start = $now.Date.AddMinutes(15 * ([math]::Floor($now.TimeOfDay.TotalMinutes / 15) + 1))
    $trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 15)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal
}
