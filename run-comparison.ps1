param(
    [string]$InputPath = (Join-Path $PSScriptRoot "samples"),
    [string]$OutputPath,
    [int]$Repeat = 5,
    [int]$TimeoutSeconds = 1800,
    [int]$Threads = 4,
    [switch]$Resume
)
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Project .venv is missing. Install the locked dependencies first."
}
$arguments = @("-m", "docling_poc.comparison", "--input", $InputPath,
    "--repeat", $Repeat, "--timeout", $TimeoutSeconds, "--threads", $Threads)
if ($OutputPath) { $arguments += @("--output", $OutputPath) }
if ($Resume) { $arguments += "--resume" }
& $python @arguments
exit $LASTEXITCODE
