# Python owns config defaults and validation. Requires Python 3.8+.
param(
    [string]$Config = "",
    [ValidateSet("bind", "plan", "scrape", "complete")][string]$Action = "plan",
    [string]$Date = "", [string]$Ward = "", [string]$Beds = "",
    [string[]]$AddSource = @(), [string[]]$RemoveSource = @(),
    [string]$ExcludeNote = "", [int]$StartHour = -1,
    [string]$DataRoot = "", [string]$Python = ""
)
$ErrorActionPreference = "Stop"
try {
    $localConfig = Join-Path $env:USERPROFILE ".workbuddy\patient-daily-summary\config.json"
    $readConfig = $localConfig
    if ($Config) { $readConfig = $Config }
    if (-not $Python -and (Test-Path -LiteralPath $readConfig)) {
        $cfg = Get-Content -LiteralPath $readConfig -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.paths.py) { $Python = [Environment]::ExpandEnvironmentVariables($cfg.paths.py) }
    }
    if (-not $Python) {
        $bundled = Join-Path $env:USERPROFILE ".workbuddy\binaries\python\envs\wxdump\Scripts\python.exe"
        if (Test-Path -LiteralPath $bundled) { $Python = $bundled }
        else {
            $found = Get-Command python -ErrorAction SilentlyContinue
            if ($found -and $found.Source -notlike '*WindowsApps*') { $Python = $found.Source }
            else { throw 'Python 3.8+ is required. Supply -Python with its executable path.' }
        }
    }
    $arguments = @((Join-Path $PSScriptRoot "daily_state.py"), $Action)
    if ($Config) { $arguments += @("--config", $Config) }
    if ($Date) { $arguments += @("--date", $Date) }
    if ($PSBoundParameters.ContainsKey('Ward')) { $arguments += @("--ward", $Ward) }
    if ($PSBoundParameters.ContainsKey('Beds')) { $arguments += @("--beds", $Beds) }
    foreach ($item in $AddSource) { $arguments += @("--add-source", $item) }
    foreach ($item in $RemoveSource) { $arguments += @("--remove-source", $item) }
    if ($PSBoundParameters.ContainsKey('ExcludeNote')) { $arguments += @("--exclude-note", $ExcludeNote) }
    if ($PSBoundParameters.ContainsKey('StartHour')) { $arguments += @("--start-hour", [string]$StartHour) }
    if ($PSBoundParameters.ContainsKey('DataRoot')) { $arguments += @("--data-root", $DataRoot) }
    $env:PYTHONIOENCODING = "utf-8"
    & $Python @arguments
    exit $LASTEXITCODE
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
