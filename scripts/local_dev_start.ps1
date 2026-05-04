# scripts/local_dev_start.ps1
# LDEV-08 (quick task 260504-g7a): Windows local-dev bootstrap.
# Loads .dev-runtime/.env (no-overwrite), verifies prereqs, starts image server.

$ErrorActionPreference = "Stop"

# --- Banner ---
Write-Host "================================================================"
Write-Host "  OmniGraph-Vault local dev bootstrap"
Write-Host "  Date: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK')"
Write-Host "  Cwd:  $PWD"
Write-Host "================================================================"

# --- UTF-8 for stdout (cp1252 trap; see docs/LOCAL_DEV_SETUP.md sec 8) ---
$env:PYTHONIOENCODING = "utf-8"
Write-Host "[OK ] PYTHONIOENCODING=utf-8"

# --- Load .dev-runtime/.env without overwriting existing process env ---
$envFile = Join-Path $PWD ".dev-runtime\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "[FAIL] .dev-runtime/.env not found at $envFile"
    Write-Host "       Pre-populate .dev-runtime/ first (see docs/LOCAL_DEV_SETUP.md sec 2)."
    exit 1
}
Write-Host "[OK ] .dev-runtime/.env exists"

$loaded = 0
foreach ($line in Get-Content -LiteralPath $envFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
    $idx = $trimmed.IndexOf("=")
    if ($idx -lt 1) { continue }
    $k = $trimmed.Substring(0, $idx).Trim()
    $v = $trimmed.Substring($idx + 1).Trim().Trim("'").Trim('"')
    if (-not $k) { continue }
    # No-overwrite: preserve any pre-set env (e.g. shell overrides, Hermes values)
    if (-not [Environment]::GetEnvironmentVariable($k, "Process")) {
        [Environment]::SetEnvironmentVariable($k, $v, "Process")
        $loaded++
    }
}
Write-Host "[OK ] loaded $loaded var(s) from .dev-runtime/.env (no-overwrite)"

# --- Prereq: SA JSON (only when vertex_gemini mode) ---
$provider = [Environment]::GetEnvironmentVariable("OMNIGRAPH_LLM_PROVIDER", "Process")
if ($provider -eq "vertex_gemini") {
    $saPath = Join-Path $PWD ".dev-runtime\gcp-paid-sa.json"
    if (-not (Test-Path $saPath)) {
        Write-Host "[FAIL] .dev-runtime/gcp-paid-sa.json missing (required for vertex_gemini mode)"
        exit 1
    }
    Write-Host "[OK ] .dev-runtime/gcp-paid-sa.json exists"
} else {
    Write-Host "[--] vertex_gemini mode not active (OMNIGRAPH_LLM_PROVIDER=$provider); skipping SA JSON check"
}

# --- Prereq: OMNIGRAPH_BASE_DIR (if set) points at an existing dir ---
$baseDir = [Environment]::GetEnvironmentVariable("OMNIGRAPH_BASE_DIR", "Process")
if ($baseDir) {
    if (-not (Test-Path -LiteralPath $baseDir -PathType Container)) {
        Write-Host "[FAIL] OMNIGRAPH_BASE_DIR=$baseDir is not an existing directory"
        exit 1
    }
    Write-Host "[OK ] OMNIGRAPH_BASE_DIR exists: $baseDir"
} else {
    Write-Host "[WARN] OMNIGRAPH_BASE_DIR unset; using Hermes default (~/.hermes/omonigraph-vault)"
}

# --- Prereq: articles.db ---
$articlesDb = Join-Path $PWD ".dev-runtime\data\articles.db"
if (-not (Test-Path $articlesDb)) {
    Write-Host "[FAIL] .dev-runtime/data/articles.db missing (DB sanity check)"
    exit 1
}
Write-Host "[OK ] .dev-runtime/data/articles.db exists"

# --- Prereq: venv python ---
$venvPython = Join-Path $PWD "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[FAIL] venv\Scripts\python.exe missing — activate venv or re-create it"
    exit 1
}
Write-Host "[OK ] venv\Scripts\python.exe exists"

# --- Start image server on port 8765 (background) ---
$imgDir = if ($baseDir) { Join-Path $baseDir "images" } else { "$HOME\.hermes\omonigraph-vault\images" }
if (-not (Test-Path -LiteralPath $imgDir -PathType Container)) {
    Write-Host "[FAIL] image dir $imgDir does not exist"
    exit 1
}
$logPath = if ($baseDir) {
    Join-Path $baseDir "logs\image_server.log"
} else {
    Join-Path $PWD ".dev-runtime\logs\image_server.log"
}
$imageProc = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "http.server", "8765", "--directory", $imgDir) `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError $logPath
Write-Host "[OK ] image server started  PID=$($imageProc.Id)  URL=http://localhost:8765"
Write-Host "       logs -> $logPath"

# --- Next-step commands ---
Write-Host ""
Write-Host "Next:"
Write-Host "  venv\Scripts\python -c `"from lib.llm_complete import get_llm_func; print(get_llm_func().__name__)`""
Write-Host "  venv\Scripts\python -c `"import config; print(config.BASE_DIR)`""
Write-Host "  venv\Scripts\python ingest_wechat.py <test-url>"
Write-Host ""
Write-Host "Image server PID: $($imageProc.Id)  (Stop-Process -Id $($imageProc.Id) to kill)"
