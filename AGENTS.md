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
