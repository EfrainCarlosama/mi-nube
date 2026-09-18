param(
    [switch]$SkipInstaller,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$buildDir = Join-Path $projectRoot "build"
$distDir = Join-Path $projectRoot "dist"
$appDir = Join-Path $distDir "MiNube"
$appExe = Join-Path $appDir "MiNube.exe"
$installerExe = Join-Path $distDir "MiNubeSetup.exe"

function Assert-ProjectChild([string]$PathValue) {
    $resolved = [IO.Path]::GetFullPath($PathValue)
    $prefix = $projectRoot.TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta fuera del proyecto rechazada: $resolved"
    }
}

function Find-SignTool {
    $command = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $kits = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path -LiteralPath $kits) {
        return Get-ChildItem -LiteralPath $kits -Filter "signtool.exe" -Recurse -File |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
    return $null
}

function Find-Iscc {
    $command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Sign-Artifact([string]$PathValue, [string]$SignTool, [string]$Thumbprint) {
    $timestampUrl = if ($env:MI_NUBE_TIMESTAMP_URL) {
        $env:MI_NUBE_TIMESTAMP_URL
    } else {
        "http://timestamp.digicert.com"
    }
    & $SignTool sign /sha1 $Thumbprint /fd SHA256 /tr $timestampUrl /td SHA256 $PathValue
    if ($LASTEXITCODE -ne 0) { throw "No se pudo firmar $PathValue" }
    & $SignTool verify /pa $PathValue
    if ($LASTEXITCODE -ne 0) { throw "La firma no pudo verificarse: $PathValue" }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "No existe el entorno virtual: $python"
}

Push-Location $projectRoot
$originalPath = $env:PATH
try {
    $version = (& $python -c "import mi_nube; print(mi_nube.__version__)").Trim()
    if (-not $version) { throw "No se pudo obtener la versión de Mi Nube." }

    Assert-ProjectChild $buildDir
    Assert-ProjectChild $distDir
    foreach ($target in @($buildDir, $distDir)) {
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
    New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
    New-Item -ItemType Directory -Path $distDir -Force | Out-Null

    & $python scripts/write_runtime_config.py --output build/runtime_config.json
    if ($LASTEXITCODE -ne 0) { throw "Falló la configuración de compilación." }

    # Codex and other developer tools may prepend unrelated DLL directories to PATH.
    # Keep dependency discovery deterministic and prevent those DLLs from entering the bundle.
    $basePrefix = (& $python -c "import sys; print(sys.base_prefix)").Trim()
    $env:PATH = @(
        (Join-Path $projectRoot ".venv\Scripts"),
        $basePrefix,
        (Join-Path $basePrefix "Scripts"),
        (Join-Path $env:SystemRoot "System32"),
        $env:SystemRoot,
        (Join-Path $env:SystemRoot "System32\Wbem")
    ) -join ';'
    $env:PYTHONHASHSEED = "0"
    if (-not $env:SOURCE_DATE_EPOCH) { $env:SOURCE_DATE_EPOCH = "1789689600" }
    & $python -m PyInstaller --noconfirm --clean MiNube.spec
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $appExe)) {
        throw "PyInstaller no generó MiNube.exe."
    }

    $smokeData = Join-Path ([IO.Path]::GetTempPath()) ("mi-nube-smoke-" + [Guid]::NewGuid())
    New-Item -ItemType Directory -Path $smokeData | Out-Null
    $previousDataDir = $env:MI_NUBE_DATA_DIR
    $previousClientId = $env:MICROSOFT_CLIENT_ID
    $previousUpdateUrl = $env:MI_NUBE_UPDATE_URL
    try {
        $env:MI_NUBE_DATA_DIR = $smokeData
        $env:MICROSOFT_CLIENT_ID = ""
        $env:MI_NUBE_UPDATE_URL = ""
        $process = Start-Process -FilePath $appExe -ArgumentList "--smoke-test" -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -ne 0) { throw "El ejecutable empaquetado falló la prueba de arranque." }
    } finally {
        $env:MI_NUBE_DATA_DIR = $previousDataDir
        $env:MICROSOFT_CLIENT_ID = $previousClientId
        $env:MI_NUBE_UPDATE_URL = $previousUpdateUrl
        if (Test-Path -LiteralPath $smokeData) {
            Remove-Item -LiteralPath $smokeData -Recurse -Force
        }
    }

    $thumbprint = $env:MI_NUBE_SIGN_CERT_SHA1
    $signTool = Find-SignTool
    if ($thumbprint) {
        if (-not $signTool) { throw "Hay certificado configurado, pero SignTool no está instalado." }
        Sign-Artifact $appExe $signTool $thumbprint
    } elseif ($RequireSignature) {
        throw "Se exigió firma, pero MI_NUBE_SIGN_CERT_SHA1 no está configurado."
    } else {
        Write-Warning "Build sin Authenticode: Windows mostrará 'Editor desconocido'."
    }

    if (-not $SkipInstaller) {
        $iscc = Find-Iscc
        if (-not $iscc) {
            throw "No se encontró Inno Setup. Instala Inno Setup 7 y vuelve a ejecutar."
        }
        & $iscc "--define=MyAppVersion=$version" "installer\MiNube.iss"
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $installerExe)) {
            throw "Inno Setup no generó MiNubeSetup.exe."
        }
        if ($thumbprint) { Sign-Artifact $installerExe $signTool $thumbprint }
    }

    $artifacts = @($appExe)
    if (Test-Path -LiteralPath $installerExe) { $artifacts += $installerExe }
    $checksumLines = foreach ($artifact in $artifacts) {
        $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $([IO.Path]::GetFileName($artifact))"
    }
    Set-Content -LiteralPath (Join-Path $distDir "checksums.sha256") -Value $checksumLines -Encoding utf8

    $pyinstallerVersion = (& $python -m PyInstaller --version).Trim()
    [ordered]@{
        version = $version
        source_date_epoch = $env:SOURCE_DATE_EPOCH
        python = (& $python --version).Trim()
        pyinstaller = $pyinstallerVersion
        signed = [bool]$thumbprint
        built_at_utc = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $distDir "build-info.json") -Encoding utf8

    if ($env:MI_NUBE_INSTALLER_URL -and (Test-Path -LiteralPath $installerExe)) {
        & $python scripts/create_update_manifest.py $installerExe $env:MI_NUBE_INSTALLER_URL
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el manifiesto firmado." }
    }

    Write-Host "Build completado: Mi Nube $version"
    Write-Host "Aplicación: $appExe"
    if (Test-Path -LiteralPath $installerExe) { Write-Host "Instalador: $installerExe" }
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
