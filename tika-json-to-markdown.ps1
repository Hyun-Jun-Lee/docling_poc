# Extract the root document's content from Tika JSON, without merging embedded files.
# Usage: .\tika-json-to-markdown.ps1 -InputPath input.json -OutputPath output.md
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$InputPath,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
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

    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $jsonText = [System.IO.File]::ReadAllText($sourcePath, $strictUtf8)
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw 'Input JSON is empty.'
    }
    $documents = @(ConvertFrom-Json -InputObject $jsonText -ErrorAction Stop)
    if ($documents.Count -eq 0 -or $null -eq $documents[0]) {
        throw 'Input JSON contains no document.'
    }

    # Tika 4.x uses tk:content; older exports may use X-TIKA:content.
    $contentProperty = $documents[0].PSObject.Properties['tk:content']
    if ($null -eq $contentProperty) {
        $contentProperty = $documents[0].PSObject.Properties['X-TIKA:content']
    }
    if ($null -eq $contentProperty) {
        throw 'Root document has no content field. Generate JSON with --jsonRecursive.'
    }
    if ($contentProperty.Value -isnot [string]) {
        throw 'Root document content must be a string.'
    }
    $content = $contentProperty.Value
    if ([string]::IsNullOrWhiteSpace($content)) {
        Write-Warning 'Root document content is empty; the Markdown file will contain no body text.'
    }

    $destinationDirectory = [System.IO.Path]::GetDirectoryName($destinationPath)
    [System.IO.Directory]::CreateDirectory($destinationDirectory) | Out-Null
    $temporaryPath = Join-Path $destinationDirectory ([System.IO.Path]::GetRandomFileName())
    # JSON parsing already decodes escaped newlines. Preserve the content verbatim.
    [System.IO.File]::WriteAllText($temporaryPath, $content, $strictUtf8)
    if ([System.IO.File]::Exists($destinationPath)) {
        [System.IO.File]::Replace($temporaryPath, $destinationPath, $null)
    } else {
        [System.IO.File]::Move($temporaryPath, $destinationPath)
    }
    $temporaryPath = $null
    Write-Host "Saved UTF-8 Markdown: $destinationPath"
} finally {
    if ($temporaryPath -and [System.IO.File]::Exists($temporaryPath)) {
        [System.IO.File]::Delete($temporaryPath)
    }
}
