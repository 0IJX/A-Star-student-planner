param(
    [string]$Version = "1.0.0",
    [switch]$Sign,
    [string]$CertPath = "",
    [string]$CertPassword = "",
    [string]$CertSha1 = "",
    [string]$CertSubject = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$DigestAlgorithm = "SHA256"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

function Resolve-CommandPath {
    param(
        [string[]]$Names
    )
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) {
            return $cmd.Source
        }
    }
    return $null
}

function Find-InnoCompiler {
    $isccCandidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup\ISCC.exe")
    )

    foreach ($path in $isccCandidates) {
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }

    $cmdPath = Resolve-CommandPath -Names @("iscc", "ISCC.exe")
    if ($cmdPath) {
        return $cmdPath
    }

    $roots = @(
        "C:\Program Files (x86)",
        "C:\Program Files",
        (Join-Path $env:LOCALAPPDATA "Programs")
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        $matches = Get-ChildItem -LiteralPath $root -Directory -Filter "Inno Setup*" -ErrorAction SilentlyContinue
        foreach ($dir in $matches) {
            $candidate = Join-Path $dir.FullName "ISCC.exe"
            if (Test-Path -LiteralPath $candidate) {
                return $candidate
            }
        }
    }

    return $null
}

function Find-SignTool {
    $manualCandidates = @(
        "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
        "C:\Program Files\Windows Kits\10\bin\x64\signtool.exe"
    )

    foreach ($candidate in $manualCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    $kitsRoots = @(
        "C:\Program Files (x86)\Windows Kits\10\bin",
        "C:\Program Files\Windows Kits\10\bin"
    )

    foreach ($root in $kitsRoots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        $versionDirs = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object -Property Name -Descending
        foreach ($dir in $versionDirs) {
            $x64 = Join-Path $dir.FullName "x64\signtool.exe"
            if (Test-Path -LiteralPath $x64) {
                return $x64
            }
            $x86 = Join-Path $dir.FullName "x86\signtool.exe"
            if (Test-Path -LiteralPath $x86) {
                return $x86
            }
        }
    }

    return (Resolve-CommandPath -Names @("signtool", "signtool.exe"))
}

function Sign-File {
    param(
        [string]$SignToolPath,
        [string]$FilePath
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        throw "Cannot sign missing file: $FilePath"
    }

    $args = @("sign", "/fd", $DigestAlgorithm, "/td", $DigestAlgorithm, "/tr", $TimestampUrl)

    if ($CertPath) {
        $args += @("/f", $CertPath)
        if ($CertPassword) {
            $args += @("/p", $CertPassword)
        }
    } elseif ($CertSha1) {
        $args += @("/sha1", $CertSha1)
    } elseif ($CertSubject) {
        $args += @("/n", $CertSubject)
    } else {
        throw "No certificate selector provided."
    }

    $args += @($FilePath)
    Write-Host "Signing: $FilePath"
    & $SignToolPath @args
    if ($LASTEXITCODE -ne 0) {
        throw "Code signing failed for $FilePath with exit code $LASTEXITCODE."
    }
}

if (-not $CertPassword -and $env:SIGN_CERT_PASSWORD) {
    $CertPassword = $env:SIGN_CERT_PASSWORD
}

$iscc = Find-InnoCompiler

if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup was not found."
    Write-Host "Install it, then run this script again."
    Write-Host "Winget command:"
    Write-Host "  winget install --id JRSoftware.InnoSetup -e"
    exit 1
}

$issPath = Join-Path (Get-Location) "installer\AStarStudentPlanner.iss"
if (-not (Test-Path -LiteralPath $issPath)) {
    throw "Installer script not found: $issPath"
}

if ($Sign) {
    if ($CertPath -and -not (Test-Path -LiteralPath $CertPath)) {
        throw "Certificate file not found: $CertPath"
    }
    if (-not $CertPath -and -not $CertSha1 -and -not $CertSubject) {
        throw "Use one of these with -Sign: -CertPath, -CertSha1, or -CertSubject."
    }
    $signToolPath = Find-SignTool
    if (-not $signToolPath) {
        throw "SignTool was not found. Install Windows SDK SignTool, then retry."
    }
    Write-Host "Using SignTool: $signToolPath"
}

Write-Host "Building app EXE first..."
& "$PSScriptRoot\build_exe.ps1" -Version $Version
if ($LASTEXITCODE -ne 0) {
    throw "EXE build failed with exit code $LASTEXITCODE."
}

$builtExe = Join-Path (Get-Location) "dist\AStarStudentPlanner\AStarStudentPlanner.exe"
if ($Sign) {
    Sign-File -SignToolPath $signToolPath -FilePath $builtExe
}

Write-Host "Creating installer with version $Version ..."
& $iscc "/DMyAppVersion=$Version" $issPath
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed with exit code $LASTEXITCODE."
}

$setupFile = Join-Path (Get-Location) ("dist\installer\AStarStudentPlanner_Setup_{0}.exe" -f $Version)
if ($Sign) {
    Sign-File -SignToolPath $signToolPath -FilePath $setupFile
}

Write-Host ""
Write-Host "Installer done."
if ($Sign) {
    Write-Host "Signed build complete."
}
Write-Host "Check: $setupFile"
