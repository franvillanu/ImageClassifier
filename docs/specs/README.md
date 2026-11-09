# Specs-Driven Development (SDD) for Image Classifier

**Rule: behaviour is defined in a spec, proven by a test, and only then implemented.**
A change that is not traceable `why → spec → test → code` is not done.

## Why this exists

Visual and lifecycle bugs (flicker, wrong window state, overlay glitches) regressed silently because
nothing recorded what the *correct* behaviour was or why the code was shaped that way. Specs record
**what must be true and why**; tests make it executable; the traceability test stops either from
drifting. See [ARCHITECTURE.md](ARCHITECTURE.md) for the system the specs sit on. The planning role
for larger work is in `.sdd/roles/architect.md` (goals/non-goals, design, contracts, edge cases, plan,
acceptance); its output becomes the spec.

## Index

| Spec | Area | Status |
|---|---|---|
| [SPEC-001-fullscreen-and-modals.md](SPEC-001-fullscreen-and-modals.md) | Fullscreen transitions, overlays, tooltips | Active, fully tested |
| [SPEC-002-slideshow-controls.md](SPEC-002-slideshow-controls.md) | Slideshow floating controls, settings dialog, mode changes | Active, in progress |
| [SPEC-003-classifier-view.md](SPEC-003-classifier-view.md) | Classifier photo view: fit, zoom, position | Active, started |

Backlog (write the spec *before* touching these areas): navigation and preloading, slideshow playback engine,
editor, updates, config persistence, favorites/compare/export, i18n.

## The workflow (mandatory, in this order)

1. **Understand.** Read [ARCHITECTURE.md](ARCHITECTURE.md) and the spec of the area. For a bug, follow the
   evidence-first `diagnose` protocol: observed symptom, measured evidence, working hypothesis, never a
   guess presented as a cause. Keep temporary probes out of the repo.
2. **Spec.** Add or change requirements in a `SPEC-NNN-*.md` *first*. Each requirement is a table row
   `| XX-n | requirement | why |` with a stable ID. Never reuse or renumber an ID; mark it `retired` instead.
3. **Test.** Write the test that cites the ID (`tests/test_spec_*.py`). For a bug fix, prove it fails on
   the old behaviour.
4. **Implement** the smallest change that makes the tests pass.
5. **Verify.** `py -m pytest -q` is green (includes `test_spec_traceability.py`). For UI/timing behaviour
   the unit tests are not enough: exercise it in the real app (see "Verifying visual behaviour").
6. **Close the loop.** Update the spec's *Evidence* / *Decision log*, add the customer-facing line in
   `docs/release_notes.txt` (see AGENTS.md), commit and push on the session branch.

## Requirement format

```
| ID   | Requirement (testable, present tense) | Why |
| FS-1 | Changing fullscreen state creates no helper window. | A cover window forced an extra repaint. |
```

- One behaviour per row, observable from outside (state, geometry, event counts), not implementation.
- Cite the ID in the test docstring and in the module's `REQUIRES` list.
- `tests/test_spec_traceability.py` fails if: an ID has no test, a test cites an unknown ID, a spec is
  missing from the index above, or an ID is defined twice.

## Verifying visual behaviour (what unit tests cannot see)

Offscreen Qt has no GL compositor, so flicker cannot be asserted in pytest. Use the event-count method
used for SPEC-001: install an application event filter, run the interaction windowed and fullscreen,
and count top-level `Expose`/`Resize` events and `Paint` waves (paints more than ~25 ms apart). Record
the before/after numbers in the spec's *Evidence* section. Run probes from a scratch directory, with
`QStandardPaths.setTestModeEnabled(True)` so the user's real config is never touched.

## Definition of done

- [ ] Spec updated (or confirmed unchanged) and indexed
- [ ] Every new requirement has a test citing its ID; bug fixes proven failing before the fix
- [ ] `py -m pytest -q` green
- [ ] Real-app check done for UI behaviour, or explicitly reported as not verified
- [ ] `docs/release_notes.txt` line added for user-visible changes
- [ ] One branch for the session; committed and pushed
