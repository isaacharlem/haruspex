# Haruspex — dashboard design

Bronze-age divination meets flight telemetry: a scientific instrument with a
mythological name. Warm, etched, precise. Explicitly NOT the default AI
dashboard (no near-black blue, no neon accents, no Inter).

## Tokens

Defined as CSS variables in `src/index.css`; everything derives from them.

| Token | Value | Use |
|---|---|---|
| `--ink` | `#14110C` | canvas (warm umber-black, not blue-black) |
| `--ink-raised` | `#1B1712` | cards, panels (derived: ink + 4% bone) |
| `--ink-well` | `#0F0C08` | chart wells, input fields (derived: ink − light) |
| `--bone` | `#E9E3D3` | primary text, target lines, focus rings |
| `--parchment` | `#B9AF99` | secondary text, labels, axis text |
| `--bronze` | `#8A6F3F` | hairlines, axes, borders, inactive |
| `--bronze-faint` | `rgba(138,111,63,.35)` | etched grid lines, dividers |
| `--verdigris` | `#4E8F7B` | healthy (aged copper — never neon) |
| `--ochre` | `#C9912E` | at-risk |
| `--oxblood` | `#A23B2E` | doomed / diverged / killed |

Status is never carried by color alone: every status renders sigil + text
label + color (see Sigils).

## Type scale

| Role | Font | Size/leading | Notes |
|---|---|---|---|
| Page title | Fraunces | 26/32, opsz auto, wght 560 | the deliberate risk: warm serif on telemetry |
| Prognosis numerals | Fraunces | 38/40, wght 540 | the big P(hit target) figures on run detail |
| Section heading | IBM Plex Sans | 13/16, wght 600, +0.04em, uppercase | quiet |
| Body | IBM Plex Sans | 14/21, wght 400 | |
| Caption / hint | IBM Plex Sans | 12/16, parchment | |
| Data (all numbers) | IBM Plex Mono | 13/16, `font-variant-numeric: tabular-nums` | metrics, steps, probabilities, dollars |
| Axis labels | IBM Plex Mono | 10/12, parchment | |

Probabilities render `P(hit target) 0.04` in mono, two decimals. Dollars
render whole: `$1,284 gross · $1,166 expected`.

## Layout concept per page

### Shell

A fixed left rail (56px, icons + labels on hover ≥ 1280px) in ink with bronze
hairline; content area scrolls. The Analyst docks as a right-side panel
(360px) on ≥ 1024px, a bottom sheet below. At 360px everything stacks
single-column; the rail becomes a bottom bar.

```
┌──┬──────────────────────────────────────────┬─────────┐
│☰ │ VitalsStrip                              │         │
│◉ │ ──────────────────────────────────────── │ Analyst │
│⚖ │                                          │ (dock)  │
│◬ │              page content                │         │
│$ │                                          │         │
│⚿ │                                          │         │
└──┴──────────────────────────────────────────┴─────────┘
```

### Fleet (`/`)

One glance answers "is anything dying, and what is it costing me?" The
VitalsStrip pins three mono figures: active runs, fleet burn $/hr, recovered
to date (gross · expected). Below, RunCards in a responsive grid (min 320px),
live runs first ordered by severity (DOOMED → AT_RISK → HEALTHY), terminal
runs dimmed behind a divider. Filters (status, tag, text) sit right of the
strip as quiet bronze-outline controls.

```
│ ACTIVE 8   BURN $74/hr   RECOVERED $1,284 · $1,166   [status][tag][search] │
│ ┌RunCard────────┐ ┌RunCard────────┐ ┌RunCard────────┐                      │
│ │ name      ◬AT │ │ name      ●OK │ │ name     ✕DOOM│                      │
│ │ ~~~~~\__,     │ │ ~~~~\___      │ │ ~~~~/‾‾⟋⟋     │  ← trace + mini fan  │
│ │ P(hit) 0.42   │ │ P(hit) 0.81   │ │ P(div) 0.93   │                      │
│ │ step 4.1k/10k │ │ step 2.0k/10k │ │ $20/hr  ◷3:12 │                      │
│ └───────────────┘ └───────────────┘ └───────────────┘                      │
```

### Run detail (`/runs/:id`)

Left: the instrument — TraceCanvas with the prognosis fan filling ~60% width,
metric tabs (loss / grad_norm / lr) above it. Right column: the three
prognosis numerals stacked in Fraunces with mono labels, then
ForecastComponentsPanel (curve family weights as etched bars, divergence
features as labeled mono values, calibration badge), then EventTimeline.
Header carries name, sigil, tags, GPU line, burn $/hr, and the Kill run
button (bronze outline, oxblood on hover) → KillConfirmDialog (type the run
name; shows grace period and checkpoint age).

```
│ gpt2-small-bf16  ◬ AT_RISK   [pretrain]   8×H100 $20/hr      [Kill run]    │
│ ┌────────────────────────────────────┐  P(hit target)   0.42               │
│ │ loss ▾                             │  P(diverge)      0.31               │
│ │ 6 ┤\                               │  P(plateau)      0.27               │
│ │   │ \_                             │  ── calibrating (n 12/30) ──        │
│ │ 4 ┤   ‾\__                  ⟋ q90  │  components ▸ pow3 .61 exp3 .31     │
│ │   │       ‾‾~~~~⊙━━━━━━━━━━─ q50  │  z∆grad 1.2  jump 0.04  rise 0.4    │
│ │ 2 ┤ ─ ─ ─ ─ ─ ─ target─ ─ ⟍ q10  │  ───────────────────────────        │
│ │   └┬────────┬────────┬───────┬────│  ◷ events                           │
│ │    0       2.5k     5k     10k    │  12:41 WARN p_diverge 0.72          │
│ └────────────────────────────────────┘  12:44 KILL_ISSUED (policy #3)      │
```

### Policies (`/policies`)

Master-detail: list left (name, enabled toggle, version, scope tags), editor
right. The editor is a form (signal/op/value/after-progress/sustained/action
fields with constrained inputs) with a raw-JSON toggle — both views edit the
same definition; invalid JSON or schema errors render inline under the
editor. "Dry run" opens a bottom drawer replaying the candidate against
history: would-have-fired rows (run, progress, signal value, gross/expected
dollars) and totals, with the stated assumptions. Empty state: "No policies
yet. Create one — start from the kill-doomed template."

### Calibration (`/calibration`)

Honesty page. Two ReliabilityDiagrams side by side (hit target / diverge):
10 bins, observed rate vs mean forecast against a bronze diagonal, bin mass
as bar thickness. Above each: Brier raw → calibrated in mono with a
BrierSparkline of fit history, n samples, and the calibrated/calibrating
badge ("calibrating — 12 of 30 runs").

### Ledger (`/ledger`)

Window selector (7/30/90 days). Two large mono totals, labeled honestly:
"gross freed compute" and "expected value, forecast-weighted" with a caption
explaining the difference in one sentence. LedgerTable below: killed run,
when, GPU, $/hr, gross, expected. Empty state: "No kills in this window.
The ledger fills when a policy (or you) stops a doomed run."

### Keys (`/settings/keys`)

Two blocks: "This dashboard" (the key the browser uses, stored locally,
re-enterable) and "API keys" (admin table: name, prefix, scopes, created,
revoke; create form shows the plaintext exactly once with a copy affordance
and a bone warning line). First-visit gate: when no dashboard key is stored,
every page renders the connect card instead of data.

## Sigils

Etched 12px SVG glyphs, 1.5px stroke, paired with text labels:

- HEALTHY `●` filled circle, verdigris
- AT_RISK `◬` open triangle, ochre
- DOOMED `✕` saltire, oxblood
- COMPLETED `◆` filled diamond, bone
- DIVERGED `✕` saltire, oxblood (label distinguishes from DOOMED)
- KILLED `⊘` slashed circle, oxblood
- LOST `◌` dotted circle, parchment

## Signature element — the prognosis fan

All visual boldness concentrates here; everything else stays quiet.

Geometry: from the head of the live trace `(step_now, y_now)` five 1px lines
fan to budget-end at the latest forecast's final-value quantiles
`(budget_steps, q10|q25|q50|q75|q90)`. Each line is a quadratic Bézier whose
control point continues the trace's local slope (the fan grows out of the
curve, not off a hinge). The q10–q90 envelope fills at 7% status-color
opacity. Lines stroke in a gradient from `--bronze` at the head into the
run's status color at budget-end; the median (q50) is 1.5px and 1.4×
brighter. A bone dashed hairline marks the target value across the canvas.

Motion: on each `forecast.updated` the five endpoints tween to their new
positions over 400ms `cubic-bezier(.25,.1,.25,1)` (d3 transition on path
`d`). The live trace carries a comet head: a 2.5px status-color dot with a
soft 6px halo, opacity pulsing 0.6→1.0 over 2.4s. Status changes cross-fade
a card's accent over 300ms. Nothing else moves.

`prefers-reduced-motion: reduce`: fan snaps (no tween), comet halo static,
cross-fades instant.

## Quality floor

- Responsive to 360px: cards stack, rail becomes bottom bar, Analyst becomes
  a bottom sheet, tables scroll horizontally inside their card.
- Focus: visible 2px bone focus ring (`outline: 2px solid var(--bone);
  outline-offset: 2px`) on every interactive element.
- Esc closes dialogs/drawers; dialogs trap focus; toasts are polite live
  regions.
- Charts carry `aria-label` summarizing latest value and forecast, e.g.
  "loss 3.41 at step 4,100; P(hit target) 0.42, median final 3.05".
- Color never the only channel: sigil + label always accompany status color.
- Single dark theme. It is an instrument.

## Copy

Sentence case, plain verbs. "Kill run" → toast "Run killed". Errors say what
happened and how to fix it ("The API rejected this key. Re-enter it in
Settings → Keys."). Empty states invite action. Probabilities as
`P(hit target) 0.04`, mono.

## Critique (one pass, §13.2) and revisions

*Would I produce this for any generic dashboard?* Three findings, revised
above:

1. **Generic**: the fan as straight lines off the trace head read like any
   confidence cone. Revision: Bézier continuation of the local slope + the
   bronze→status gradient strokes — an augural diagram, not an error bar.
2. **Generic**: status chips as rounded color pills (the default dashboard
   move). Revision: etched sigil glyphs + uppercase mono labels; no pills
   anywhere.
3. **Generic**: VitalsStrip as three "stat cards" with big numbers in boxes.
   Revision: a single hairline-bounded strip, label-above-figure in mono,
   no boxes — closer to a cockpit annunciator row.

## Addendum — the bounded-and-etched pass (2026-06-09)

Field problems found at extreme viewports, and the system answers:

- **Stretched-viewBox SVGs scaled type grotesquely on wide screens.** All
  instruments (TraceCanvas, ReliabilityDiagram) now render at measured pixel
  size via `useMeasure` (ResizeObserver); fonts and stroke weights are
  constant at any viewport.
- **Warmup transients crushed the y-domain.** LTTB preserves extremes, so the
  trace domain uses an IQR fence (median + 8×IQR, floored at p90) with the
  recent tail, target, and fan quantiles always re-widening it — a divergence
  blowup stays visible, a warmup cliff enters from off-plot.
- **Boxes expanded infinitely.** Content is capped at 1600px and centered in
  the shell; fleet cards mint via `auto-fill, minmax(300px, 1fr)` with a
  460px ceiling; sparse pages (Calibration, Ledger) center as narrower
  columns.
- **The Analyst dock resizes.** Drag the left edge (320–640px, persisted in
  localStorage; arrow keys on the handle; Home resets). Desktop dock is
  sticky full-height with internal scroll — a long transcript can no longer
  stretch the page.
- **The etched layer.** `.tablet` (outer hairline + inset ghost hairline +
  raking light; `.tablet-link` lifts on hover), `.rune-rule` section headers
  (◆ + fading hairline), `.etched-rule` double hairline under page titles,
  paper-grain + atmospheric glows on the body, thin bronze scrollbars,
  toast slide-ins and fade-ups — all reduced-motion aware. Prognosis
  numerals carry per-outcome meter bars (verdigris/oxblood/ochre).
