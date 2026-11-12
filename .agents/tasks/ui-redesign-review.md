# ACIP demo UI redesign: review (pass 2)

Redesign of `ui/` (Global Payments-inspired brand tokens, light default with persisted dark, decision journey, why panel, agent cards, help drawer, guided tour, tooltips, empty state) plus an additive backend change that persists and exposes per-agent rationale and evidence. Pass 2 confirms the three pass-1 fixes (gauge value, approve screenshot, control border contrast) and the tablet title clipping fix. No blocking concerns remain.

Watch for: (1) at 768px the header title truncates to "Decision Intel..." (confirmed, cosmetic, non-blocking); (2) the Policy agent card in a row with a taller neighbour leaves a blank area (confirmed, cosmetic).

**Verdict**: APPROVED

## High-level view

Brand colour lives only in `brand.css`, with the approximation header and a note that `index.html` repeats `--brand-deep` for `theme-color`. Engine defaults appear only in `thresholds.ts` and the help/content copy. Theme is light unless `acip.theme=dark`. The frontend only presents returned data: `why.ts` classifies the engine's own explanation, and the only timing shown is the browser round trip. The replay is labelled as a replay. The backend change adds nullable columns with a legacy-query fallback and tests. No dependencies were added, and the lockfile, Dockerfile, nginx, vite config and start scripts are untouched.

<details>
<summary>Issues (3)</summary>

1. **Truncated tablet title (confirmed, non-blocking)** — at 768px the h1 shows "Decision Intel...". Hide the connection pill text or let the title wrap at that width.
2. **Uneven agent card heights (confirmed, non-blocking)** — grid stretch leaves empty space under Policy. Use `align-items: start` or equal-content layout.
3. **Failed explain load flips phase to error (possible, non-blocking)** — a failed `loadExplain` dispatches the global `failed` action even with a good result shown. Scope it to the trace view.

</details>

<details>
<summary>Details</summary>

### Verification run
- `uv run pytest libs/acip-common services -q`: 128 passed.
- UI: lint, format:check, typecheck clean; 118 tests pass in 14 files; build ok with a separate HelpDrawer chunk.
- Contrast recomputed independently (WCAG formula) for every pair in `contrast-pairs.ts`: 0 failures. The new control borders measure 3.90 (light on white), 3.63 (light on page), 3.72 and 4.39 (dark on surface and page), all at or above 3:1.
- Brand hex outside the allowed files: only `meta theme-color` in `index.html`, now documented in `brand.css`. No threshold literals outside `thresholds.ts` and content copy. Scenario payload fields are unchanged (the diff only reformats `scenarioBody` and adds icon, story and demonstrates). `package.json` only gained scripts. `package-lock.json`, Dockerfile, nginx and start scripts are not in the diff. `VITE_CHECKOUT_API_URL` handling is unchanged.

### Visual judgement
Screenshots were re-shot after the fixes. In `04-approve-d-light.png` the approve result now renders and the gauge value "0.019" sits clear of the hub. Light theme reads clean and on-brand: deep-blue header and primary buttons, teal accent strip, restrained status chips that always pair icon and word. The approve banner, why panel, six-stage journey and agent cards make each step understandable. The replay notice is labelled as not live timing. The brand slot shows a text "ACIP" wordmark with "in partnership with Global Payments", and no logo is fabricated. Help drawer, tour, tooltips and empty state are present in the screenshots. Dark theme is coherent.

### Honesty of derived content
Stages 2, 5 and 6 carry "not returned by the API" notes. Agent cards show "General description" always and "Reported by this agent" only when the API supplies it. The veto sentinel composite is hidden ("Scoring skipped").

### Backend
`ADD COLUMN IF NOT EXISTS` in bootstrap and seed, new projector params appended after the original four, `reads.py` falls back to the legacy query on `UndefinedColumn`, and tests cover extra keys and legacy rows. The API doc is updated.

</details>

<details>
<summary>File map</summary>

`ui/src/styles/*` tokens, brand, base, layout, components; `ui/src/components/{layout,input,journey,agents,help,ui}`; `ui/src/domain/*`; `ui/src/content/*`; `ui/src/state/useCheckoutRun.ts`; `ui/src/config/thresholds.ts`; backend `bootstrap.py`, `seed.py`, `postgres_projector.py`, `reads.py` with tests and `docs/06-api-contracts.md`. Full diff: `git diff a376561..HEAD`.

</details>
