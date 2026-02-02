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

# Check if version changed
$versionChanged = $false
if (Test-Path 'version.txt') {
  # Get current version from version.txt
  $versionContent = Get-Content 'version.txt' -Raw
  if ($versionContent -match 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') {
    $currentVersion = "$($matches[1]).$($matches[2]).$($matches[3]).$($matches[4])"
    
    # Check if version.txt was modified in this branch compared to main
    $mainVersion = ''
    git show main:version.txt 2>$null | ForEach-Object {
      if ($_ -match 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') {
        $mainVersion = "$($matches[1]).$($matches[2]).$($matches[3]).$($matches[4])"
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

# If version changed, run Release.bat before creating PR
if ($versionChanged) {
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
      
      # Stage all website and changelog files updated by Release.bat
      git add docs/index.html docs/changelog.html 2>$null
      
      # If there are changes, commit them
      $status = git status --porcelain -- docs/
      if ($status) {
        # Extract short version (e.g., "2.0" from "2.0.0.0")
        $shortVersion = $currentVersion -replace '^(\d+\.\d+)\..*$', '$1'
        git commit -m "release: v$shortVersion - website and changelog updates"
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

# Add release note if version changed
if ($versionChanged) {
  $bodyLines += ''
  $bodyLines += '## Release'
  $bodyLines += "- ✅ Version updated to $currentVersion"
  $bodyLines += "- ✅ Installer built and GitHub Release created automatically"
}

$body = $bodyLines -join "`n"

$url = gh pr create --head $branch --title $title --body $body

if (-not $url) {
  Write-Error 'No se pudo crear el PR'
  exit 1
}

$pr = ($url -split '/')[ -1 ]

gh pr merge $pr --squash --delete-branch

# Check for uncommitted changes and stash them before switching branches
$uncommitted = git status --porcelain
if ($uncommitted) {
  Write-Host ''
  Write-Host "⚠️  Stashing uncommitted changes before switching to main..." -ForegroundColor Yellow
  git stash push -m "Auto-stash before PR merge checkout"
}

git checkout main
if ($LASTEXITCODE -ne 0) {
  Write-Error "Failed to checkout main. Uncommitted changes may need to be committed or stashed manually."
  exit 1
}

git pull

Write-Host ''
Write-Host "PR creado: $url"
Write-Host 'Mergeado a main ✅'
Write-Host 'Branch local actualizado'

# If version changed, create GitHub Release AFTER merge
if ($versionChanged) {
  $shortVersion = $currentVersion -replace '^(\d+\.\d+)\..*$', '$1'
  Write-Host ''
  Write-Host "🚀 Creating GitHub Release for v$shortVersion..." -ForegroundColor Cyan
  
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
  Write-Host "🎉 Release v$shortVersion ready!" -ForegroundColor Green
  Write-Host "   Website deploying to Cloudflare Pages..." -ForegroundColor Cyan
  Write-Host "   Download link will be available once deployment completes." -ForegroundColor Cyan
}