# Agent Protocols

**Git protocol:** Whenever you make file changes and you're on `main`, create a new branch, commit, and push. See [docs/guides/GIT-PROTOCOL.md](docs/guides/GIT-PROTOCOL.md) or `.cursor/rules/` for git sections.

## Git Workflow (MANDATORY)

**Before ANY file edits:**

1. Check branch: `git branch --show-current`
2. If on `main` → create branch: `git checkout -b fix/description` (or `feature/`, `refactor/`, `docs/`, `chore/`, `release/`)
3. Push branch: `git push -u origin fix/description`
4. Make your changes
5. Commit and push: `git add . && git commit -m "type: description" && git push`

**Never commit directly to `main`.** Always create a branch first.

## Branch Types

- `fix/` - Bug fixes
- `feature/` - New features
- `refactor/` - Code refactoring
- `docs/` - Documentation updates
- `chore/` - Maintenance tasks
- `release/` - Release preparation

## References

- [docs/guides/GIT-PROTOCOL.md](docs/guides/GIT-PROTOCOL.md) - Complete git protocol
- `.cursor/rules/git-branch-gate.mdc` - Branch creation rules
- `.cursor/rules/git-commit-push-gate.mdc` - Commit/push rules

## Specs-Driven Development (MANDATORY)

Behaviour is defined in a spec, proven by a test, then implemented. Full process: [docs/specs/README.md](docs/specs/README.md); system map: [docs/specs/ARCHITECTURE.md](docs/specs/ARCHITECTURE.md).

**For every change, in order:**

1. Read `docs/specs/ARCHITECTURE.md` and the spec of the area you touch. For bugs, diagnose with evidence first (observed symptom, measurement, hypothesis); never present a guess as the cause.
2. Add or change the requirement (`| XX-n | requirement | why |`) in a `docs/specs/SPEC-*.md` **before** the code. New area without a spec: write it first and add it to the README index.
3. Write the test citing the requirement ID in `tests/test_spec_*.py`; for a bug fix, show it fails on the old behaviour.
4. Implement, then run `py -m pytest -q`. `tests/test_spec_traceability.py` must pass (every requirement has a test, no test cites an unknown ID).
5. UI/timing behaviour cannot be proven offscreen: measure it in the real app (event-count method in the specs README) or say plainly it is unverified.
6. Update the spec's Evidence/Decision log, add the release-notes line, commit and push on the session branch.

Never delete or weaken a spec test to make a change pass: change the spec first, with the reason.

## Release notes (MANDATORY)

The release script (`.vscode/pr_create_merge_update.ps1` → `Release.bat`) bumps the version automatically but **stops if `docs/release_notes.txt` has no entry for the new version**. Customers see those notes in the app, so they are written by hand.

**Before telling the user to run the merge script:**

1. Work out the next version: the latest published version + 1 patch (the script bumps it itself; do not edit `version.txt`, `pyproject.toml`, `package.json` or `__init__.py`).
2. Add one line at the top of `docs/release_notes.txt`, after the `#` comments: `X.Y.Z|English|Español|YYYY-MM-DD`. Separate points with ` • ` and start each with `new:`, `changed:` or `fixed:` (same tags in both languages). Customer-facing only, no internal changes.
3. Commit and push it on the working branch together with the changes.

Do not ask the user whether to add the note: just add it.

## One branch per session (MANDATORY)

Use a single branch for all changes in a session. Never create extra branches or switch branches without telling the user which one they are on: they test by relaunching the app from the checked-out branch.
