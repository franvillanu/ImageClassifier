$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot
Set-Location '..'
Set-Location (Resolve-Path '.')

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

# Check if version changed (3-digit version: major.minor.patch)
$versionChanged = $false
$currentVersion = ''
if (Test-Path 'version.txt') {
  $versionContent = Get-Content 'version.txt' -Raw
  if ($versionContent -match 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') {
    $currentVersion = "$($matches[1]).$($matches[2]).$($matches[3])"
    
    $mainVersion = ''
    git show main:version.txt 2>$null | ForEach-Object {
      if ($_ -match 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') {
        $mainVersion = "$($matches[1]).$($matches[2]).$($matches[3])"
      }
    }
    
    if ($mainVersion -and $currentVersion -ne $mainVersion) {
      $versionChanged = $true
      Write-Host ''
      Write-Host "⚠️  Version changed detected: $mainVersion → $currentVersion" -ForegroundColor Yellow
      Write-Host "This will trigger a release build..." -ForegroundColor Yellow
    }
  }
}

# If no GitHub release exists for current version, we must run Release.bat first (build installer)
$releaseNeeded = $false
if ($currentVersion) {
  $tag = "v$currentVersion"
  $oldErr = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $null = gh release view $tag 2>&1
    if ($LASTEXITCODE -ne 0) {
      $releaseNeeded = $true
      Write-Host ''
      Write-Host "⚠️  No GitHub Release $tag yet → will run Release.bat to build installer first" -ForegroundColor Yellow
    }
  } finally {
    $ErrorActionPreference = $oldErr
  }
}

# Run Release.bat when version changed OR when release for current version is missing
if ($versionChanged -or $releaseNeeded) {
  Write-Host ''
  Write-Host "🚀 Running Release.bat to build installer and create GitHub Release..." -ForegroundColor Cyan
  
  # Check if Release.bat exists
  if (-not (Test-Path 'Release.bat')) {
    Write-Warning "Release.bat not found. Skipping release build."
  } else {
    # Run Release.bat non-interactively (set NON_INTERACTIVE to skip pause)
    $env:NON_INTERACTIVE = "1"
    $process = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "Release.bat" -Wait -NoNewWindow -PassThru
    Remove-Item Env:\NON_INTERACTIVE
    
    if ($process.ExitCode -ne 0) {
      Write-Warning "Release.bat failed or was cancelled (exit code: $($process.ExitCode)). Continuing with PR creation anyway..."
    } else {
      Write-Host "✅ Release build completed!" -ForegroundColor Green
      
      # Reset .iss file if it was modified (build process updates version, but we don't commit it)
      $issStatus = git status --porcelain -- Image_Classifier.iss
      if ($issStatus) {
        git checkout -- Image_Classifier.iss
        Write-Host "✅ Reset Image_Classifier.iss (build artifact)" -ForegroundColor Gray
      }
      
      # Stage all website and changelog files updated by Release.bat
      # Temporarily disable error action to handle git warnings gracefully
      $oldErrorAction = $ErrorActionPreference
      $ErrorActionPreference = 'Continue'
      try {
        git add docs/index.html docs/changelog.html 2>&1 | Out-Null
      } finally {
        $ErrorActionPreference = $oldErrorAction
      }
      
      # If there are changes, commit them
      $status = git status --porcelain -- docs/
      if ($status) {
        git commit -m "release: v$currentVersion - website and changelog updates"
        Write-Host "✅ Committed website and changelog updates" -ForegroundColor Green
      }
    }
  }
}

$title = (git log -1 --pretty=%s)

$bodyLines = @(
  '## Summary'
  '- '
  ''
  '## Test plan'
  '- [ ] '
)

# Add release note if we ran a release build (version changed or release was missing)
if ($versionChanged -or $releaseNeeded) {
  $bodyLines += ''
  $bodyLines += '## Release'
  $bodyLines += "- ✅ Installer built (v$currentVersion)"
  $bodyLines += "- ✅ GitHub Release will be created after merge"
}

$body = $bodyLines -join "`n"

$url = gh pr create --head $branch --title $title --body $body

if (-not $url) {
  Write-Error 'No se pudo crear el PR'
  exit 1
}

$pr = ($url -split '/')[ -1 ]

gh pr merge $pr --squash --delete-branch

# Check for uncommitted changes before switching branches
$uncommitted = git status --porcelain
if ($uncommitted) {
  Write-Host ''
  Write-Error "Cannot switch to main: You have uncommitted changes."
  Write-Host "Uncommitted files:" -ForegroundColor Yellow
  git status --short
  Write-Host ''
  Write-Host "Please commit or stash your changes before running this script." -ForegroundColor Yellow
  Write-Host "  To commit: git add . && git commit -m 'your message'" -ForegroundColor Cyan
  Write-Host "  To stash: git stash" -ForegroundColor Cyan
  exit 1
}

git checkout main
if ($LASTEXITCODE -ne 0) {
  Write-Error "Failed to checkout main."
  exit 1
}

git pull

Write-Host ''
Write-Host "PR creado: $url"
Write-Host 'Mergeado a main ✅'
Write-Host 'Branch local actualizado'

# Check if GitHub Release exists for current version (3-digit tag e.g. v2.0.1)
$currentVersion = ''
if (Test-Path 'version.txt') {
  $versionContent = Get-Content 'version.txt' -Raw
  if ($versionContent -match 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') {
    $currentVersion = "$($matches[1]).$($matches[2]).$($matches[3])"
  }
}

$releaseExists = $false
if ($currentVersion) {
  $tag = "v$currentVersion"
  $oldErr = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $null = gh release view $tag 2>&1
    if ($LASTEXITCODE -eq 0) {
      $releaseExists = $true
      Write-Host "✅ GitHub Release $tag already exists" -ForegroundColor Green
    }
  } finally {
    $ErrorActionPreference = $oldErr
  }
}

# Create or update GitHub Release when version changed or when release is missing
if (($versionChanged -or -not $releaseExists) -and $currentVersion) {
  Write-Host ''
  if ($releaseExists) {
    Write-Host "🚀 Updating GitHub Release v$currentVersion (uploading new installer)..." -ForegroundColor Cyan
  } else {
    Write-Host "🚀 Creating GitHub Release v$currentVersion..." -ForegroundColor Cyan
  }
  
  # Check if GitHub token exists
  $hasToken = $false
  if ($env:GITHUB_TOKEN) {
    $hasToken = $true
  } elseif (Test-Path '.github_token') {
    $hasToken = $true
  }
  
  if ($hasToken) {
    py scripts/create_github_release.py
    if ($LASTEXITCODE -eq 0) {
      Write-Host "✅ GitHub Release created!" -ForegroundColor Green
    } else {
      Write-Warning "GitHub Release creation failed, but website will still deploy."
    }
  } else {
    Write-Host "⚠️  Skipping GitHub Release (no token found)." -ForegroundColor Yellow
    Write-Host "   Set GITHUB_TOKEN env var or create .github_token file to enable."
  }
  
  Write-Host ''
  Write-Host "🎉 Release v$currentVersion ready!" -ForegroundColor Green
  Write-Host "   Website deploying to Cloudflare Pages..." -ForegroundColor Cyan
  Write-Host "   Download link will be available once deployment completes." -ForegroundColor Cyan
}