param(
    [string]$Version = "1.0.0",
    [string]$Company = "A-Star Student Planner Team",
    [string]$Description = "A-Star Student Planner Desktop App",
    [string]$ProductName = "A-Star Student Planner"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt

# Prepare an .ico file from the logo so EXE and installer use a proper Windows icon.
@'
from pathlib import Path
from PIL import Image

root = Path(".").resolve()
src = root / "assets" / "kid-icon.png"
dst = root / "assets" / "app.ico"

if not src.exists():
    raise SystemExit(f"Logo not found: {src}")

img = Image.open(src).convert("RGBA")
side = min(img.width, img.height)
left = (img.width - side) // 2
top = (img.height - side) // 2
crop = img.crop((left, top, left + side, top + side))
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
crop.save(dst, format="ICO", sizes=sizes)
print(f"Prepared icon: {dst}")
'@ | & ".venv\Scripts\python.exe" -

$buildDir = Join-Path (Get-Location) "build"
if (-not (Test-Path -LiteralPath $buildDir)) {
    New-Item -ItemType Directory -Path $buildDir | Out-Null
}

$parts = @($Version -split '\.')
while ($parts.Count -lt 4) {
    $parts += "0"
}
$parts = $parts[0..3] | ForEach-Object { [int]$_ }
$versionTuple = "$($parts[0]), $($parts[1]), $($parts[2]), $($parts[3])"

$versionFile = Join-Path $buildDir "version_info.txt"
@"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($versionTuple),
    prodvers=($versionTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', '$Company'),
          StringStruct('FileDescription', '$Description'),
          StringStruct('FileVersion', '$Version'),
          StringStruct('InternalName', 'AStarStudentPlanner'),
          StringStruct('OriginalFilename', 'AStarStudentPlanner.exe'),
          StringStruct('ProductName', '$ProductName'),
          StringStruct('ProductVersion', '$Version')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -LiteralPath $versionFile -Encoding UTF8

$dataArg = "data\STUDEN_1.CSV;data"
$logoArg = "assets\kid-icon.png;assets"
$icoDataArg = "assets\app.ico;assets"
$iconArg = "assets\app.ico"

& ".venv\Scripts\pyinstaller.exe" `
  --noconfirm `
  --clean `
  --windowed `
  --name "AStarStudentPlanner" `
  --icon $iconArg `
  --version-file $versionFile `
  --add-data $dataArg `
  --add-data $logoArg `
  --add-data $icoDataArg `
  main.py

Write-Host "Build done: dist\AStarStudentPlanner\AStarStudentPlanner.exe"
