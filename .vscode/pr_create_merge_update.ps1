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

# ── 1.2. Release: if release_notes.txt has a version that is not published yet, build it now ─────
# One task does everything: version bump, build, sign, commit, PR, merge and publish.
py scripts/auto_bump_version.py --needs-release
$releaseCheck = $LASTEXITCODE
$releasePending = ($releaseCheck -eq 10)
if ($releaseCheck -eq 10) {
  Write-Host ""
  Write-Host "Release pendiente: construyendo y firmando con Release.bat..." -ForegroundColor Cyan
  $env:NON_INTERACTIVE = '1'
  cmd.exe /c ".\Release.bat"
  if ($LASTEXITCODE -ne 0) {
    Write-Error 'Release.bat fallo. Revisa el error de arriba (nada se ha mergeado ni publicado).'
    exit 1
  }
} elseif ($releaseCheck -ne 0) {
  Write-Error 'No se pudo comprobar si hay un release pendiente (auto_bump_version.py fallo).'
  exit 1
}

# ── 1.5. Commit what Release.bat prepared (version bump, changelog, website) ───
# Only these release-owned files are staged, so the bump always travels with the PR.
$releaseFiles = @(
  'version.txt', 'pyproject.toml', 'package.json', 'image_classifier/__init__.py',
  'Image_Classifier.iss', 'docs/release_notes.txt', 'docs/changelog.html', 'docs/index.html'
)
$pendingRelease = @(git status --porcelain -- $releaseFiles)
if ($pendingRelease.Count -gt 0) {
  $releaseVersion = ''
  if ((Get-Content 'version.txt' -Raw) -match 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') {
    $releaseVersion = "$($matches[1]).$($matches[2]).$($matches[3])"
  }
  git add -- $releaseFiles
  git commit --quiet -m "release: prepare v$releaseVersion"
  if ($LASTEXITCODE -ne 0) {
    Write-Error 'No se pudo hacer commit de los archivos de release'
    exit 1
  }
  Write-Host "Archivos de release incluidos: release: prepare v$releaseVersion ✅"
}

# ── 1.6. Push the branch: the PR is built from the pushed branch, never from local-only commits ─────
git push --quiet -u origin $branch
if ($LASTEXITCODE -ne 0) {
  Write-Error "No se pudo hacer push de la rama $branch"
  exit 1
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

  $publishedAsset = $null
  # "release not found" on stderr is expected for a new tag; Windows PowerShell 5.1 would treat it as fatal under 'Stop'
  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  $releaseJson = gh release view $tag --repo $releasesRepo --json assets 2>$null
  $viewExitCode = $LASTEXITCODE
  $ErrorActionPreference = $previousPreference
  if ($viewExitCode -eq 0 -and $releaseJson) {
    $publishedAsset = ($releaseJson | ConvertFrom-Json).assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
  }

  if ($publishedAsset) {
    # Same name is not same file: never skip silently when the local installer is a different build.
    $localHash = if (Test-Path $installerPath) { 'sha256:' + (Get-FileHash $installerPath -Algorithm SHA256).Hash.ToLower() } else { $null }
    if ($localHash -and $publishedAsset.digest -and $localHash -ne $publishedAsset.digest) {
      Write-Warning "$tag is already published but its installer differs from Output\$assetName. Users would not get this build."
      Write-Warning "Run Release.bat again (it bumps the version automatically), then this task. To overwrite $tag instead: py scripts/create_github_release.py"
    } else {
      Write-Host "Release $tag already published in $releasesRepo ✅"
    }
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

# ── 9. Verify the release really happened (never trust that every step printed OK) ──────────────
# Checks version in main, published installer checksum vs the local build, and the in-app notes.
if ($releasePending) {
  Write-Host ""
  Write-Host "Verificando el release publicado..." -ForegroundColor Cyan
  py scripts/verify_release.py
  if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "RELEASE NO VERIFICADO ❌ El PR se mergeo pero el release publicado no coincide con lo construido." -ForegroundColor Red
    Write-Host "Revisa los problemas de arriba. Para repetir solo la publicacion: py scripts/create_github_release.py" -ForegroundColor Red
    exit 1
  }
  Write-Host "Release verificado ✅" -ForegroundColor Green
}
