# Extract document content and metadata without PowerShell pipeline encoding conversion.
# Compatible with Windows PowerShell 5.1 and PowerShell 7 on Windows.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$InputPath,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$javaProcess = $null
$outputStream = $null
$temporaryPath = $null

try {
    $sourcePath = (Resolve-Path -LiteralPath $InputPath).ProviderPath
    if (-not [System.IO.File]::Exists($sourcePath)) {
        throw "Input must be a file: $sourcePath"
    }
    $destinationPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath(
        $OutputPath
    )
    if ([string]::Equals($sourcePath, $destinationPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Input and output paths must be different.'
    }

    $tikaDirectory = Join-Path $PSScriptRoot 'tika-app-4.0.0'
    $tikaJar = Join-Path $tikaDirectory 'tika-app-4.0.0.jar'
    if (-not (Test-Path -LiteralPath $tikaJar -PathType Leaf)) {
        throw "Tika distribution not found: $tikaJar"
    }
    $tikaConfig = Join-Path $PSScriptRoot 'tika-config.json'
    if (-not (Test-Path -LiteralPath $tikaConfig -PathType Leaf)) {
        throw "Tika configuration not found: $tikaConfig"
    }

    # Prefer the active shell, then discover Java installed after this shell started.
    $javaCommand = Get-Command java.exe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $javaExecutable = if ($javaCommand) { $javaCommand.Source } else { $null }
    if (-not $javaExecutable) {
        $javaCandidates = @()
        foreach ($scope in @('Process', 'User', 'Machine')) {
            $configuredHome = [Environment]::GetEnvironmentVariable('JAVA_HOME', $scope)
            if ($configuredHome) {
                $javaCandidates += Join-Path $configuredHome 'bin\java.exe'
            }
            $configuredPath = [Environment]::GetEnvironmentVariable('Path', $scope)
            foreach ($entry in ($configuredPath -split ';')) {
                if ($entry.Trim()) {
                    $expandedEntry = [Environment]::ExpandEnvironmentVariables($entry.Trim().Trim('"'))
                    $javaCandidates += Join-Path $expandedEntry 'java.exe'
                }
            }
        }
        $javaExecutable = $javaCandidates |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
    }
    if (-not $javaExecutable) {
        throw 'Java not found. Install Java 17+ and configure PATH or JAVA_HOME.'
    }

    $destinationDirectory = [System.IO.Path]::GetDirectoryName($destinationPath)
    [System.IO.Directory]::CreateDirectory($destinationDirectory) | Out-Null
    $temporaryPath = Join-Path $destinationDirectory ([System.IO.Path]::GetRandomFileName())

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $javaExecutable
    $startInfo.WorkingDirectory = $tikaDirectory
    # Resolved Windows file paths cannot contain double quotes.
    $startInfo.Arguments = '-Dfile.encoding=UTF-8 -jar "' + $tikaJar +
        '" --config="' + $tikaConfig +
        '" --jsonRecursive --pretty-print --encoding=UTF-8 "' + $sourcePath + '"'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $outputStream = [System.IO.File]::Create($temporaryPath)
    $javaProcess = [System.Diagnostics.Process]::Start($startInfo)
    # Copy raw UTF-8 bytes; never decode stdout through a PowerShell pipeline.
    $copyTask = $javaProcess.StandardOutput.BaseStream.CopyToAsync($outputStream)
    $errorTask = $javaProcess.StandardError.ReadToEndAsync()
    $javaProcess.WaitForExit()
    $null = $copyTask.GetAwaiter().GetResult()
    $diagnostics = $errorTask.GetAwaiter().GetResult()
    $outputStream.Dispose()
    $outputStream = $null
    if ($javaProcess.ExitCode -ne 0) {
        throw "Tika failed (exit $($javaProcess.ExitCode)):`n$diagnostics"
    }

    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $jsonText = [System.IO.File]::ReadAllText($temporaryPath, $strictUtf8)
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw 'Tika returned empty output.'
    }
    $null = ConvertFrom-Json -InputObject $jsonText -ErrorAction Stop
    if ([System.IO.File]::Exists($destinationPath)) {
        [System.IO.File]::Replace($temporaryPath, $destinationPath, $null)
    } else {
        [System.IO.File]::Move($temporaryPath, $destinationPath)
    }
    $temporaryPath = $null
    if ($diagnostics.Trim()) { Write-Verbose $diagnostics.Trim() }
    Write-Host "Saved UTF-8 JSON: $destinationPath"
} finally {
    if ($outputStream) { $outputStream.Dispose() }
    if ($javaProcess) { $javaProcess.Dispose() }
    if ($temporaryPath -and [System.IO.File]::Exists($temporaryPath)) {
        [System.IO.File]::Delete($temporaryPath)
    }
}
