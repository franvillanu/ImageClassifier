# Branch–Commit–Push Protocol

**Purpose:** Single source of truth for the mandatory git workflow. All AI assistants (Claude, ChatGPT, Copilot) and contributors must follow this.

---

## The Rule

**Whenever you make changes to files in this repo:**

1. **If you're on `main`** → Create a new branch (before or immediately after making changes).
2. **Commit** all changes to that branch. Never commit directly to `main`.
3. **Push** the branch to `origin` before you finish.

---

## Checklist

- [ ] `git branch --show-current` → if `main`, run `git checkout -b <type>/<name>`
- [ ] Make your changes
- [ ] `git add .` (or specific files)
- [ ] `git commit -m "type: description"`
- [ ] `git push -u origin <branch>`
- [ ] User creates PR and merges via GitHub (assistants never merge to `main`)

---

## Commands

```bash
git branch --show-current
git checkout -b fix/foo   # or feature/bar, chore/baz, docs/readme
# ... edit files ...
git add .
git commit -m "fix: short description"
git push -u origin fix/foo
```

---

## Branch Naming

| Type    | Prefix     | Example                |
|---------|------------|------------------------|
| Feature | `feature/` | `feature/website-localization` |
| Bug fix | `fix/`     | `fix/changelog-symbol`  |
| Refactor| `refactor/`| `refactor/release-scripts`|
| Docs    | `docs/`    | `docs/build-guide`     |
| Chore   | `chore/`   | `chore/update-deps`    |
| Release | `release/` | `release/v2.0`         |

---

## Special Cases

### Release Process

When running `Release.bat`:
1. Create branch: `git checkout -b release/v2.0`
2. Run release (updates changelog, website, builds installer, creates GitHub Release)
3. Commit website changes: `git add docs/ && git commit -m "release: v2.0"`
4. Push: `git push -u origin release/v2.0`
5. Create PR to merge to `main`
6. **Merge PR using "Squash and merge"** (recommended - keeps history clean)
7. After merge, GitHub Release is already created automatically by `Release.bat`

### Website Updates

After `update_website.py` runs:
- Always commit `docs/index.html` and `docs/changelog.html` if modified
- Push to branch (never directly to `main`)

---

## References

- `.cursor/rules/git-branch-gate.mdc` – Cursor AI rules
- `.cursor/rules/git-commit-push-gate.mdc` – Cursor AI commit rules
