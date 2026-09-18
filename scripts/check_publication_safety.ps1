param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$findings = [Collections.Generic.List[object]]::new()

function Add-Finding([string]$PathValue, [string]$Reason) {
    $findings.Add([PSCustomObject]@{
        File = $PathValue
        Reason = $Reason
    })
}

function Normalize-RelativePath([string]$PathValue) {
    return $PathValue.Replace('\', '/').TrimStart('/')
}

function Get-RelativePath([string]$FullName) {
    $fullPath = [IO.Path]::GetFullPath($FullName)
    $prefix = $projectRoot.TrimEnd('\') + '\'
    if (-not $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta fuera del proyecto rechazada."
    }
    return Normalize-RelativePath $fullPath.Substring($prefix.Length)
}

function Test-FallbackExcluded([string]$RelativePath) {
    if ($RelativePath -match '^(\.git|\.venv|venv|build|dist|data|secrets|credentials|\.pytest-tmp|\.pytest_cache|\.ruff_cache|__pycache__|[^/]+\.egg-info)(/|$)') {
        return $true
    }
    if ($RelativePath -eq '.env' -or ($RelativePath -like '.env.*' -and $RelativePath -ne '.env.example')) {
        return $true
    }
    if ($RelativePath -match '(?i)(\.py[co]|\.log)$') {
        return $true
    }
    return $false
}

function Test-ForbiddenPath([string]$RelativePath) {
    if ($RelativePath -eq '.env' -or ($RelativePath -like '.env.*' -and $RelativePath -ne '.env.example')) {
        return 'configuración privada de entorno'
    }
    if ($RelativePath -match '^(data|secrets|credentials)(/|$)') {
        return 'carpeta de datos o credenciales'
    }
    if ($RelativePath -match '(?i)(\.db(?:-.*)?|\.sqlite3?|\.pfx|\.p12|\.key|\.dpapi|\.bak|\.dump|\.dmp|\.log)$') {
        return 'tipo de archivo privado prohibido'
    }
    if ($RelativePath -match '(?i)\.pem$' -and $RelativePath -ne 'src/mi_nube/assets/update_public_key.pem') {
        return 'archivo PEM no autorizado'
    }
    return $null
}

$candidatePaths = [Collections.Generic.List[string]]::new()
$git = Get-Command 'git.exe' -ErrorAction SilentlyContinue
$isProjectRepository = $false
if ($git) {
    $gitRoot = (& $git.Source -C $projectRoot rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -eq 0 -and $gitRoot) {
        $resolvedGitRoot = [IO.Path]::GetFullPath(($gitRoot | Select-Object -First 1).Trim())
        $isProjectRepository = $resolvedGitRoot.TrimEnd('\') -eq $projectRoot.TrimEnd('\')
    }
}

if ($isProjectRepository) {
    $listed = & $git.Source -C $projectRoot ls-files --cached --others --exclude-standard
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo obtener la lista segura de Git.' }
    foreach ($pathValue in $listed) {
        if ($pathValue) { $candidatePaths.Add((Normalize-RelativePath $pathValue)) }
    }
} else {
    foreach ($file in Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -File) {
        $relativePath = Get-RelativePath $file.FullName
        if (-not (Test-FallbackExcluded $relativePath)) {
            $candidatePaths.Add($relativePath)
        }
    }
}

$candidatePaths = @($candidatePaths | Sort-Object -Unique)
foreach ($relativePath in $candidatePaths) {
    $reason = Test-ForbiddenPath $relativePath
    if ($reason) { Add-Finding $relativePath $reason }
}

$textExtensions = @(
    '', '.example', '.gitignore', '.iss', '.md', '.pem', '.ps1', '.py', '.spec', '.toml', '.txt', '.yml', '.yaml'
)
$contentRules = [ordered]@{
    'clave privada PEM' = '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
    'clave de acceso de AWS' = '\bAKIA[0-9A-Z]{16}\b'
    'token de GitHub' = '\bgh[pousr]_[A-Za-z0-9]{30,}\b'
    'credencial o firma de Azure' = '(?i)(Account' + 'Key=|SharedAccess' + 'Signature=|[?&]sig=[A-Za-z0-9%+/=]{20,})'
    'token de Slack' = '\bxox[baprs]-[A-Za-z0-9-]{20,}\b'
    'clave de API de Google' = '\bAIza[0-9A-Za-z_-]{35}\b'
    'token JWT' = '\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'
    'credencial literal' = '(?i)\b(client_secret|api_key|access_token|refresh_token|password|passwd|secret_key|private_key)\b\s*[:=]\s*["''][^"''\r\n]{8,}["'']'
}

$localMarkers = [ordered]@{}
if ($env:USERPROFILE) { $localMarkers['ruta del perfil local'] = $env:USERPROFILE }
if ($env:COMPUTERNAME) { $localMarkers['nombre del equipo local'] = $env:COMPUTERNAME }

$localConfiguration = [ordered]@{}
$envFile = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
        $parts = $trimmed.Split('=', 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($key -match '(?i)(client_id|tenant_id|secret|token|password|private|key|url)' -and $value.Length -ge 16) {
            $localConfiguration[$key] = $value
        }
    }
}

foreach ($relativePath in $candidatePaths) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { continue }
    $extension = [IO.Path]::GetExtension($fullPath).ToLowerInvariant()
    if ($textExtensions -notcontains $extension) { continue }

    $content = Get-Content -LiteralPath $fullPath -Raw -ErrorAction Stop
    foreach ($rule in $contentRules.GetEnumerator()) {
        if ($content -match $rule.Value) { Add-Finding $relativePath $rule.Key }
    }
    foreach ($marker in $localMarkers.GetEnumerator()) {
        if ($marker.Value.Length -ge 5 -and $content.IndexOf($marker.Value, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            Add-Finding $relativePath $marker.Key
        }
    }
    foreach ($setting in $localConfiguration.GetEnumerator()) {
        if ($content.Contains($setting.Value)) {
            Add-Finding $relativePath "valor local de $($setting.Key)"
        }
    }

    foreach ($match in [regex]::Matches($content, '(?i)[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})')) {
        $domain = $match.Groups[1].Value.ToLowerInvariant()
        if ($domain -notmatch '(^|\.)(example\.(com|org|net)|contoso\.com|test|invalid)$') {
            Add-Finding $relativePath 'correo electrónico no reservado'
        }
    }
}

$uniqueFindings = @($findings | Sort-Object File, Reason -Unique)
if ($uniqueFindings.Count -gt 0) {
    Write-Host 'COMPROBACIÓN BLOQUEADA: se encontraron elementos que deben revisarse.' -ForegroundColor Red
    $uniqueFindings | Format-Table -AutoSize
    exit 1
}

Write-Host "Comprobación segura: $($candidatePaths.Count) archivos candidatos, sin datos privados detectados." -ForegroundColor Green
Write-Host 'No se publicó ni transfirió ningún archivo.'
exit 0
