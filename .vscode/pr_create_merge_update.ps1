$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot
Set-Location '..'
$repoRoot = (Resolve-Path '.').Path

# ── 1. Ensure we're on a feature branch ─────────────────────────────────────
$branch = (git rev-parse --abbrev-ref HEAD).Trim()

if ($branch -eq 'main') {
  $timestamp = Get-Date -Format 'yyyyMMdd-HHmm'
  $newBranch = "fix/from-main-$timestamp"
  git checkout -b $newBranch
  if ($LASTEXITCODE -ne 0) {
    Write-Error 'No se pudo crear la rama. Cambia manualmente a una rama feature.'
    exit 1
  }
  $branch = $newBranch
  Write-Host "Rama creada automaticamente: $branch"
}

# ── 2. Fetch latest main ─────────────────────────────────────────────────────
Write-Host "Actualizando origin/main..."
git fetch origin main --quiet
if ($LASTEXITCODE -ne 0) {
  Write-Error 'No se pudo hacer fetch de origin/main'
  exit 1
}

# ── 3. Check for conflicts before creating the PR ────────────────────────────
Write-Host "Comprobando conflictos con main..."

$mergeBase = (git merge-base HEAD origin/main).Trim()
$mergeOutput = git merge-tree $mergeBase origin/main HEAD 2>&1
$hasConflicts = ($mergeOutput | Where-Object { $_ -match "^<<<<<<< " }).Count -gt 0

if ($hasConflicts) {
  Write-Host ""
  Write-Host "Conflictos detectados con main. Resuelvelos antes de continuar." -ForegroundColor Red
  exit 1
}

Write-Host "Sin conflictos con main ✅"

# ── 4. Check if a PR already exists for this branch ─────────────────────────
$existingPrJson = gh pr list --head $branch --base main --state open --json number,url 2>$null
$existingPr = $null
if ($existingPrJson) {
  $parsed = $existingPrJson | ConvertFrom-Json
  if ($parsed.Count -gt 0) {
    $existingPr = $parsed[0]
  }
}

if ($existingPr) {
  $pr  = $existingPr.number
  $url = $existingPr.url
  Write-Host "PR existente detectado: $url"
} else {
  $title = (git log -1 --pretty=%s).Trim()
  $body  = "## Summary`n- `n`n## Test plan`n- [ ] "

  $url = gh pr create --head $branch --base main --title $title --body $body
  if ($LASTEXITCODE -ne 0 -or -not $url) {
    Write-Error 'No se pudo crear el PR'
    exit 1
  }
  $pr = ($url -split '/')[-1]
  Write-Host "PR creado: $url"
}

# ── 5. Squash-merge and delete remote branch ─────────────────────────────────
gh pr merge $pr --squash --delete-branch
if ($LASTEXITCODE -ne 0) {
  Write-Error "No se pudo mergear el PR $pr"
  exit 1
}

# ── 6. Switch to main and pull ───────────────────────────────────────────────
git checkout main
if ($LASTEXITCODE -ne 0) {
  Write-Error 'No se pudo cambiar a main'
  exit 1
}

git pull --ff-only
if ($LASTEXITCODE -ne 0) {
  Write-Error 'No se pudo actualizar main'
  exit 1
}

git fetch --prune origin

# ── 7. Publish the release to the public releases repo ───────────────────────
# The publish script is idempotent: it creates the release, or edits it and re-uploads the installer.
$currentVersion = ''
if (Test-Path 'version.txt') {
  $versionContent = Get-Content 'version.txt' -Raw
  if ($versionContent -match 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') {
    $currentVersion = "$($matches[1]).$($matches[2]).$($matches[3])"
  }
}

if ($currentVersion) {
  $tag = "v$currentVersion"
  $releasesRepo = 'franvillanu/imageclassifier-releases'
  $assetName = "ImageClassifierSetup_v$currentVersion.exe"
  $installerPath = Join-Path $repoRoot "Output\$assetName"

  $assetExists = $false
  # "release not found" on stderr is expected for a new tag; Windows PowerShell 5.1 would treat it as fatal under 'Stop'
  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  $releaseJson = gh release view $tag --repo $releasesRepo --json assets 2>$null
  $viewExitCode = $LASTEXITCODE
  $ErrorActionPreference = $previousPreference
  if ($viewExitCode -eq 0 -and $releaseJson) {
    $assetExists = [bool](($releaseJson | ConvertFrom-Json).assets | Where-Object { $_.name -eq $assetName })
  }

  if ($assetExists) {
    Write-Host "Release $tag already published in $releasesRepo ✅"
  } elseif (-not (Test-Path $installerPath)) {
    Write-Warning "Installer not found at $installerPath. Run Release.bat before using this PR merge task for releases."
  } else {
    Write-Host ""
    Write-Host "Publishing $tag to $releasesRepo..." -ForegroundColor Cyan
    py scripts/create_github_release.py
    if ($LASTEXITCODE -eq 0) {
      Write-Host "GitHub Release ready: $tag" -ForegroundColor Green
    } else {
      Write-Warning "GitHub Release creation/upload failed for $tag."
    }
  }
}

# ── 8. Delete local feature branch (gh pr merge --delete-branch may have already done this) ──
if (git branch --list $branch) {
  git branch -d $branch 2>$null | Out-Null
}

Write-Host ""
Write-Host "PR: $url"
Write-Host "Mergeado a main ✅"
Write-Host "Main actualizado ✅"
Write-Host "Rama local eliminada: $branch"
