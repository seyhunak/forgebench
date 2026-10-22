# ForgeBench 20s Pitch — Design Spec (autonomous free creation)

Mode: **自主自由创作 (autonomous)**. Agent decides; no stage gates with user.
Video: **1920×1080 @ 30fps, 600 frames = 20.0s**, SFX + BGM (two delivery versions: `bgm:true/false` inputProp).

---

## Stage 0 — Product brief & requirements→execution table

**Product**: ForgeBench — reproducible, provider-agnostic benchmark harness.
Question it answers: *did customizing a model actually improve domain performance, or just add complexity?*

**Audience**: technical decision-makers — ML platform leads, DevOps/AI-eng, risk/compliance
(regulated domains). Language: **English** (repo and audience are English).

**Core selling points to land in 20s** (hard constraints from user: use-cases + demo reel):
1. Use-case frame: A/B prompt & fine-tune validation, CI regression gates, risk-aware metrics.
2. Demo reel of the real app: run → report → compare with deltas.
3. Ends on brand + repo.

**Must-show features** (feature list for shot mapping):
- Fixed synthetic test sets + manifests (datasets view)
- Run report / metrics (run detail modal)
- **Compare runs → Δ vs baseline, incl. critical false-match rate** ← the money shot
- (context) BYOK / provider-agnostic — covered in copy only, not a shot (20s budget)

**Duration/aspect/language**: 20s / 16:9 / English.
**Audio**: no user-specified BGM → agent picks at stage 6 from `assets/audio/bgm/` (tech-leaning),
SFX from `assets/audio/sfx/`. Deliver `bgm` boolean inputProp → two final renders.

**Data & privacy** (frozen before capture):
- All pages are the **local dashboard** fed by **synthetic datasets** and **mock runs**
  (`ci-baseline`, `ci-prompt` — rule-mock provider, generated data). This is public demo data
  already published in the repo README screenshots → safe to keep.
- API-key page shows `key set` (masked `mst********}QaA0`) — **no secrets** anywhere. `.env` never opened.
- No PII, no customer data, no live keys, no network egress beyond local loopback.

**Comparison pair chosen for the compare shot** (both real local runs, 60 cases):

| metric | ci-baseline | ci-prompt | Δ |
|---|---|---|---|
| Accuracy | 0.8214 | 0.8667 | **+0.0452** |
| Macro F1 | 0.7334 | 0.7776 | +0.0442 |
| Critical false-match rate | 0.0952 | 0.0667 | **−0.0286** (better) |
| Escalation recall | 0.9048 | 0.9333 | +0.0286 |
| Schema validity | 0.9333 | 1.0 | +0.0667 |

Risk message: the *expensive* error went down while accuracy went up — exactly the pitch.

## Requirement→execution decisions

| Decision | Choice | Reason |
|---|---|---|
| Template vs free | **Free creation** (recorded at mode select) | Ink Press paper/amber clashes with the dark Cobalt product; 20s ≠ 36.2s structure |
| Visual direction | **"Instrument panel"** — precision, dark, hairline, mono labels | Derived from product CSS tokens (below), not invented |
| Motion preset | 专业信赖 (enterprise/B2B): ~21f main, `cubic-bezier(0,0,0.2,1)`, no overshoot on fades; overshoot **only** where a landing metaphor exists (rows hitting slots: spring y1>1) | Dev-tool = serious/precision on the tone axis |
| Assets | **Real screenshots only**, captured from the running local dashboard at DSF 2 | Core rule: replica pages = real screenshots; dashboard runs locally |
| Styleframe | HTML key frames screenshot-verified (cheap direction check) | pipeline stage 1 |
| Storyboard | 5 shots, promo-energy-arc adapted for 20s (no breathing title cards — use-cases beat *is* the mid-card) | See timeline |
| BGM | Agent-chosen at stage 6, two renders | No user BGM specified |

## Stage 1 — Visual direction: "Instrument panel"

**Design tokens (extracted from `src/forgebench/static/style.css` — product is the source):**

- Surfaces: `--paper oklch(15.5% .012 258)` ≈ `#0d0f14` · `--surface 19%` ≈ `#14171e` ·
  `--surface-2 22.5%` ≈ `#191d25` · `--line oklch(29% .016 258)` ≈ `#2a2f3a`
- Ink: `--ink 94%` ≈ `#eef1f6` · `--ink-2 74%` · `--ink-3 58%`
- Accent (Cobalt): `--accent oklch(63% .19 256)` ≈ `#3b82f6`-family · `--focus 72% .17 256`
- Signals: `--success oklch(74% .16 152)` · `--danger oklch(67% .2 25)` · `--info oklch(71% .13 220)`
- Type: **Space Grotesk** (display) / **Inter** (body) / **JetBrains Mono** (mono labels) —
  mono uppercase + letter-spacing for kickers/labels (`01 · CREDENTIALS` pattern)
- Geometry: radius 4/6/10px, 1px hairlines, `--ease cubic-bezier(.2,.7,.2,1)` @150ms
- Motifs: numbered mono section labels, side-rail nav, hairline tables, dense metric rows

**Motion personality tokens** (brand → motion): energy = low-mid · tone = serious/precision →
`EASE_OUT = cubic-bezier(0,0,0.2,1)`, main move ≈ 21f, entrances 18–24f, holds ≥30f after
settle, no decorative glow bursts (single-point light ok, group glints = cheap), no handheld shake.

**Machine color vs page color** (for the scan shot): page content stays Cobalt; the *machine's
vision* uses the product's **danger/signal** token (`oklch(67% .2 25)` ≈ `#e5623c`) — strictly
separated so "the page" and "what the analyzer flags" never blur.

## Stage 2 — Feature → shot mapping (each grammar leads exactly once)

| Feature | Shot | Card / grammar (lead once) | Backup |
|---|---|---|---|
| Positioning headline | S1 open | **blur-slide** — word-by-word 3-channel same-ease reveal | type-entrance-moves (rejected: too playful) |
| Use cases (3) | S2 panel | **row-embed** — rows drop, rotateX flatten, accent seam flash on landing | slam-entrance (rejected: 3 rows ≠ 1 KPI slam) |
| Real product: run report | S3 | **PageCam 2.5D** camera glide over the run-detail texture (camera is not an element grammar) | type-and-filter (needs 3 interactive states) |
| Real product: compare Δ | S4 peak | **scanline-annotate-focus** — scan → bracket snap → typed machine label on the risk row | before-after-slider (rejected: only one real page state) |
| Brand sign-off | S5 | **letterspace-materialize** — wordmark crystallizes + tagline + hold ≥30f | logo-shrink-wordmark-lockup (rejected: neon ring too energetic for precision brand) |

## Stage 3 — Storyboard & frame timeline (production release, 600f)

| # | from → to | dur | content | key motion | SFX anchors |
|---|---|---|---|---|---|
| S1 | 0 → 88 | 88f | Dark instrument bg (hairline grid, vignette) + mono kicker `DOMAIN EVAL HARNESS` + headline **"Measure domain adaptation, not just model intelligence."** (accent on *domain adaptation*) + sub `ForgeBench · reproducible, provider-agnostic evaluation` | **blur-slide**: words 0.38em→0, blur 18→0, opacity 0→1, same ease-out, ~4f stagger (L1 from f6, L2 after, sub from f32); hold | see stage-6 pin table |
| S2 | 88 → 195 | 107f | Floating panel `WHAT USE CASES RUN HERE` + 3 rows embed: `PROMPT & FINE-TUNE A/B VALIDATION` · `REGRESSION GATES ON EVERY PR` · `RISK-AWARE METRICS · CRITICAL FALSE-MATCH RATE` | **row-embed**: row drops from above, rotateX flattens, accent seam flash at embed; cues `CUE=[14,24,33]` accelerate (10→7f gap), `FLIGHT=13` → seats at +27/+37/+46; hold ≥30f | see stage-6 pin table |
| S3 | 195 → 330 | 135f | Full-page 2x texture of run-detail modal (report of `ci-prompt`) in a browser-plane frame | **PageCam**: slight rot → straighten, push-in toward metric strip, end hold; caption bottom | camera whoosh + settle thud |
| S4 | 330 → 475 | 145f | Full-page texture of **Compare runs** table (ci-baseline vs ci-prompt) | **scanline-annotate-focus**: 70f constant-speed scan (`SCAN_FROM=-30 → SCAN_TO=900`, starts lf6), L-brackets spring in on 4 target rows (`TARGETS=[1,2,3,5]`), compact numeral-only delta chips in the right page margin (`LABEL_X=TABLE_X+TABLE_W+20`), status → SIGNOFF at lf84; slow 1.000→1.035 push; hold ~62f | see stage-6 pin table |
| S5 | 475 → 600 | 125f | Instrument bg → **FORGEBENCH** wordmark crystallizes (lowercase), tagline `Measure what customization actually changed.` + line `github.com/seyhunak/forgebench` | **letterspace-materialize**: all strokes draw in parallel (shared START=16 / DUR=52, pathLength-normalized), hold ≥30f | see stage-6 pin table |

**Seams** (from `transition/shot-transitions.md`, chosen at implementation): S1→S2 push,
S2→S3 push-to-frame (page plane enters), S3→S4 whip/cut on motion, S4→S5 flash-cut on the
label chime. Budget comes out of adjacent shots.

**Copy discipline**: no repeated tagline (headline in S1, different sign-off line in S5),
every shot delivers new information, captions on all non-card shots (no silent passages).

## Stage 4 — Asset list

- `public/textures/live/compare-full.png` (2x full page, compare table w/ deltas) + `layout.json` boxes for metric rows
- `public/textures/live/report-full.png` (2x, run-detail modal over results)
- `public/textures/live/results-full.png`, `datasets-full.png` (backups / context)
- Fonts: Space Grotesk / Inter / JetBrains Mono into `public/fonts/`

Captured via `scripts/capture.py` (dashboard on `:8501`) → 2× textures + `src/live-layout.json`
(row/label boxes for PageCam targets). All data synthetic/mock local runs, no secrets/PII.

## Stage 5 — Build & picture lock (QA-verified)

- Remotion 4.0.245 scaffold in `promo-video/`; shots in `src/shots/S1..S5`, seams via `FlashCut`.
- **Styleframe skipped** (recorded): strict token-derived design system + real screenshots make a
  separate HTML key-frame stage redundant — Remotion stills per shot serve as the QA check.
- Design changes made during build (this supersedes stage 3 where they differ):
  - **S1 rebalanced to 88f** (was 80f): word stagger + sub needed the extra 8f to hold ≥30f after
    settle; S2 shrinks to 107f, rest of timeline unchanged.
  - **S4 label redesign**: original plan (typed signal label over the row) collided with the page
    texture's own text. Fixes: `TARGETS=[1,2,3,5]` (rows[0] is the table header — an earlier
    `[0,1,2,4]` off-by-one attached deltas to the wrong rows), **numeral-only delta chips in the
    right page margin** instead of inline labels, top-left status scrim + bottom caption scrim
    (260px) for legibility, camera flat/centered on `FOCUS_Y≈788`.
  - **S4 scan timing**: constant speed `SCAN_LEN=70f` from lf6 → `FIRE=[63,67,71,75]`
    (4f-clamped), `statusDone = lf > LAST_FIRE+8` → SIGNOFF at lf84, ~62f hold.
- **Picture locked**: all five shots QA-verified via rendered stills
  (S1 f58, S2 f162, S3 f291, S4 f370/395/405/420, S5 f491/515/543/570).

## Stage 6 — Sound (BGM + SFX pins)

**BGM**: `bgm-tech-house.mp3` — chosen quantitatively: first-20s 4s-window RMS arc runs
−18.6 → −10.8 dB, tracking the storyboard energy curve (low open → mid push → outro peak); the
outro 三拍 lands on the track's loudest section. Envelope `[0,30,550,600] → [0,0.34,0.34,0]`
(1s fade-in, 1.7s fade-out), bed at 0.34 to leave SFX headroom.

**Peak-alignment method** (`src/audio.ts`, formula from sound-design §4.6):
`from = round(targetPeak − PEAK_F[src] − OUTPUT_AUDIO_OFFSET_F)`
- `PEAK_F[src]` — per-file energy-peak lag, measured on the copies in `public/audio/`
  (ffmpeg decode → 1/30s RMS windows → 3-frame smoothed argmax): swoosh-quick 9, transition-soft
  12, transition-snap 3, whoosh-fast 21, pop 0, data-scan 10, lock-quick 0, lock-digital 6,
  gear-lock-metallic 7, riser-cine 30, impact-deep-whoosh 17, sparkle 43.
- `OUTPUT_AUDIO_OFFSET_F = 2.03` — whole-pipeline audio delay, measured 2026-10-22 on
  the rendered mp4: FFT cross-correlation of 5 SFX probes placed every source onset at
  `from + 2.03f` (spread 2.02–2.04, no per-file drift). The naive AAC-priming estimate
  (1.28f = 2048 samples) undershot by a steady +0.75f ≈ one MP3 decode frame (1152
  samples); the measured total replaces it. Source peak lag (`PEAK_F`) and pipeline
  offset are kept in separate books. Re-probe after re-render: residual ≤0.5f.
- Verified numerically: each pin's peak lands within ±0.5f of target (integer
  `Sequence.from` rounding) — plus the end-to-end render probe below.

**Pin table** (15 pins + BGM; expressions relative to `SHOT_S*_START`, volumes 0.2–0.6):

| target (rel) | file | vol | note |
|---|---|---|---|
| S1+10 | swoosh-quick | 0.42 | title motion peak (clamps to from=0) |
| S2+0, S3+0, S5+0 | transition-soft ×3 | 0.40 | peak lands on each cut |
| S2+27/+37/+46 | snap / pop / snap | 0.40/0.34/0.28 | row seats, alternating near-samples + descending ladder |
| S4+0 | whoosh-fast | 0.45 | S3→S4 whip, tail hands off to scan |
| S4+50 | data-scan | 0.55 | file only 60f (flat ~30f): placed over table crossing + bracket burst, seam whoosh carries lf0–30 |
| S4+63, +75 | lock-quick, lock-digital | 0.45/0.45 | first & last bracket; middle two deliberately unvoiced |
| S4+84 | gear-lock-metallic | 0.50 | SIGNOFF status flip |
| S5+33 | riser-cine | 0.40 | riser climax mid-draw (dur 144) |
| S5+68 | impact-deep-whoosh | 0.55 | **film's SFX peak**, lands on wordmark stamp (dur 121) |
| S5+93 | sparkle | 0.45 | tagline/repo settle (dur 136) |

**Two-version delivery**: BGM mounted behind `bgm` inputProp (default `true`), SFX unaffected —
`props-nobgm.json` = `{"bgm":false}` renders the no-BGM cut from the same timeline.
