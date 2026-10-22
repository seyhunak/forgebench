# Review brief — ForgeBench 20s pitch (stage-7 final review)

You are an independent review agent in a clean context. You did not participate in
production. Do not assume anything beyond what the inputs below state. Where an input
is missing, write "无法验证 / cannot verify" — do not guess the production baseline.

## Inputs (read these)

| input | path |
|---|---|
| This brief | `promo-video/REVIEW-BRIEF.md` |
| Product brief + requirements→execution table + visual direction + storyboard + audio spec | `promo-video/DESIGN.md` |
| Review checklist | `~/.config/opencode/skills/video-shotcraft/references/final-review.md` |
| Visual/technical quality rules | `~/.config/opencode/skills/video-shotcraft/references/aesthetic-rules.md` |
| Shot cards used | `references/shots/typography/blur-slide.md`, `references/shots/ui-entrance/row-embed.md`, `references/shots/camera/depth-layer-moves.md` (PageCam), `references/shots/effects/scanline-annotate-focus.md`, `references/shots/opening/letterspace-materialize.md` (all under `~/.config/opencode/skills/video-shotcraft/`) |
| Final films | `promo-video/out/forgebench-20s-bgm.mp4` (with BGM), `promo-video/out/forgebench-20s-nobgm.mp4` (SFX only) |
| Per-shot keyframes (from the with-BGM render) | `promo-video/out/review/f010 … f595.png` (24 frames) |
| Shot source (for verifying grammar/params) | `promo-video/src/shots/S1..S5.tsx`, `promo-video/src/audio.ts` |
| Live layout used for page boxes | `promo-video/src/live-layout.json` |

## Creation mode

**自主自由创作 (autonomous free creation)** — the agent recorded its own decisions at
each stage in DESIGN.md; there was no user sign-off mid-stream. Judge against the
recorded decisions, not against an imagined external baseline.

## Product video brief (frozen requirements)

- 20.0s / 1920×1080 / 30fps / 600 frames / English.
- Must show: (1) use-case frame — prompt & fine-tune A/B validation, CI regression
  gates, risk-aware metrics; (2) real-app demo reel — run → report → compare deltas;
  (3) brand + repo outro.
- Data safety: only synthetic/mock local runs; no secrets/PII in captured assets.
- Deliver two renders (with BGM / no BGM) from one timeline.

## Shot list (final storyboard, as recorded)

| shot | frames | content | grammar |
|---|---|---|---|
| S1 | 0–87 | kicker `DOMAIN EVAL HARNESS` + headline "Measure domain adaptation, not just model intelligence." + sub | blur-slide word reveal |
| S2 | 88–194 | use-case panel, 3 rows seat into slots (seats at local 27/37/46) | row-embed |
| S3 | 195–329 | run-detail report modal, PageCam glide | camera move (depth-layer) |
| S4 | 330–474 | Compare-runs table; scan lf6→76, brackets fire at lf 63/67/71/75, SIGNOFF at lf84 | scanline-annotate-focus |
| S5 | 475–599 | wordmark letterspace-materialize (draw 16→68), tagline, repo line, hold | letterspace-materialize |

## Audio (as recorded)

- BGM `bgm-tech-house.mp3`, envelope [0,30,550,600]→[0,0.34,0.34,0], gated by `bgm` inputProp.
- 15 SFX pins in `src/audio.ts`; peak-aligned via
  `from = round(target − PEAK_F[src] − OUTPUT_AUDIO_OFFSET_F)`,
  `OUTPUT_AUDIO_OFFSET_F = 2.03` (measured 2026-10-22 by FFT cross-correlation of 5
  probes on the rendered mp4: placed at from+2.03f, spread 2.02–2.04).
- Volumes 0.2–0.6; impact-deep-whoosh 0.55 = film's SFX peak.
- Long samples riser/impact/sparkle carry explicit `durationInFrames`.

## Measured facts (verified with ffmpeg on the render — cite, don't re-derive)

- with-BGM render: `mean_volume −21.3 dB`, `max_volume −2.9 dB` (no clipping).
- Both renders are 600 frames, from the same timeline; only the BGM track differs.
- SFX files used and their source peaks: swoosh-quick −0.1, transition-soft −0.9,
  transition-snap −4.0, whoosh-fast −1.3, pop −2.0, data-scan −2.1, lock-quick −0.3,
  lock-digital −1.8, gear-lock −1.0, riser-cine 0.0, impact-deep-whoosh −0.4,
  sparkle −6.7 dB (all ≥ −12 dB → none needs gain >1).

## What to produce

Follow the report format in `final-review.md`: numbered verdicts (P/F/V/S/B/D/A/Q),
each problem with a frame number or keyframe filename. Finish with must-fix /
should-fix / cannot-verify lists. No vague "looks fine" verdicts; do not mark items
pass without evidence from a frame or an input document.
