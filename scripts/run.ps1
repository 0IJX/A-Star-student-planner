Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

& (Join-Path (Get-Location) "start.cmd") @args
exit $LASTEXITCODE
