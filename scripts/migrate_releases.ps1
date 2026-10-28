# One-time: copy the existing releases (v2.0 .. v2.0.7) from the source repo to the
# public releases-only repo. Oldest first so the newest ends up as "Latest".
# Idempotent: tags that already exist in the target are skipped.
#
# Usage: powershell -File scripts/migrate_releases.ps1 [-DryRun]
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$source = 'franvillanu/ImageClassifier'
$target = 'franvillanu/imageclassifier-releases'

function ConvertTo-VersionKey([string]$tag) {
  $parts = ($tag.TrimStart('v') -split '\.') | ForEach-Object { [int]$_ }
  while ($parts.Count -lt 3) { $parts += 0 }
  return '{0:D4}.{1:D4}.{2:D4}' -f $parts[0], $parts[1], $parts[2]
}

$tags = (gh release list --repo $source --limit 100 --json tagName | ConvertFrom-Json).tagName |
  Sort-Object { ConvertTo-VersionKey $_ }
if (-not $tags) { throw "No releases found in $source" }
$newest = $tags[-1]

$work = Join-Path ([System.IO.Path]::GetTempPath()) 'ic-release-migration'
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Path $work | Out-Null

foreach ($tag in $tags) {
  gh release view $tag --repo $target 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { Write-Host "skip   $tag (already in $target)"; continue }

  $info = gh release view $tag --repo $source --json name,body | ConvertFrom-Json
  $dir = Join-Path $work $tag
  New-Item -ItemType Directory -Path $dir | Out-Null
  gh release download $tag --repo $source --dir $dir
  $files = Get-ChildItem $dir -File | ForEach-Object { $_.FullName }
  if (-not $files) { Write-Warning "no assets for $tag, skipping"; continue }

  $notes = Join-Path $dir 'notes.md'
  Set-Content -Path $notes -Value $info.body -Encoding utf8
  $title = if ($info.name) { $info.name } else { "Image Classifier $($tag.TrimStart('v'))" }

  $ghArgs = @('release', 'create', $tag) + $files + @('--repo', $target, '--title', $title, '--notes-file', $notes)
  if ($tag -eq $newest) { $ghArgs += '--latest' } else { $ghArgs += '--latest=false' }

  if ($DryRun) { Write-Host "dryrun gh $($ghArgs -join ' ')"; continue }
  Write-Host "create $tag ($($files.Count) asset(s))"
  gh @ghArgs
  if ($LASTEXITCODE -ne 0) { throw "Failed to create $tag" }
}

Remove-Item $work -Recurse -Force
Write-Host "Done. Check: gh release list --repo $target"
