param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $baseDir "venv\Scripts\python.exe"
$syncFile = Join-Path $baseDir "sync_commands.py"

if (-not (Test-Path $pythonExe)) {
    throw "가상환경 파이썬을 찾지 못했습니다: $pythonExe"
}

& $pythonExe $syncFile @Args
