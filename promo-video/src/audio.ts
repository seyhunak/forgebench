// Audio — stage 6, after picture lock. Two layers (sound-design.md §1):
//
//  • BGM: one bed across all 600f, volume envelope fades in/out, mounted only
//    when the `bgm` inputProp is true → two delivery renders from one timeline.
//  • SFX: every pin is an EXPRESSION relative to its shot's start frame, so
//    retiming a shot never desyncs its sound (§4.5). `from` is computed through
//    sfxFrom(): the frame where the file's OWN energy peak will land on the
//    design target in the rendered output (§4.6) — two offsets sit between intent
//    the source's own peak lag (per file, measured) and the whole-pipeline
//    audio delay (per pipeline, measured once — see the constant below).
import { interpolate } from 'remotion';
import { SHOT_S1_START } from './shots/S1';
import { SHOT_S2_START } from './shots/S2';
import { SHOT_S3_START } from './shots/S3';
import { SHOT_S4_START } from './shots/S4';
import { SHOT_S5_START } from './shots/S5';

export const hasAudio = true;

// ---- pin math (§4.6) -------------------------------------------------------
// Whole pipeline delay (Remotion mix → mp3 decode → AAC encode → decode), the
// source analysis and the output offset stay in separate books: the source's
// own peak lag lives in PEAK_F below and is never folded into this constant.
//
// Measured 2026-10-22 on the rendered mp4: FFT cross-correlation of 5 SFX
// probes (swoosh-quick / whoosh-fast / gear-lock / impact / lock-quick, NCC
// 0.26–0.96) placed each source onset at from + 2.03f (2.02–2.04 spread —
// no per-file drift). The naive AAC-priming estimate 1.28f (2048 samples)
// undershot by a steady +0.75f ≈ the MP3 decode frame (1152 samples), so the
// measured total replaces it. Residual after this value: ≤0.5f, dominated by
// Math.round() on integer Sequence starts.
const OUTPUT_AUDIO_OFFSET_F = 2.03;

// Per-file energy-peak lag in frames @30fps. Measured on the copies in
// public/audio/: ffmpeg decode → 1/30s RMS windows → 3-frame smoothed argmax.
const PEAK_F: Record<string, number> = {
  'audio/sfx/transition/swoosh-quick.mp3': 9,
  'audio/sfx/transition/transition-soft.mp3': 12,
  'audio/sfx/transition/transition-snap.mp3': 3,
  'audio/sfx/transition/whoosh-fast.mp3': 21,
  'audio/sfx/ui/pop.mp3': 0,
  'audio/sfx/data/data-scan.mp3': 10,
  'audio/sfx/mech/lock-quick.mp3': 0,
  'audio/sfx/mech/lock-digital.mp3': 6,
  'audio/sfx/mech/gear-lock-metallic.mp3': 7,
  'audio/sfx/riser/riser-cine.mp3': 30,
  'audio/sfx/impact/impact-deep-whoosh.mp3': 17,
  'audio/sfx/light/sparkle.mp3': 43,
};

const sfxFrom = (targetPeakF: number, src: string) =>
  Math.max(0, Math.round(targetPeakF - (PEAK_F[src] ?? 0) - OUTPUT_AUDIO_OFFSET_F));

// ---- BGM -------------------------------------------------------------------
// bgm-tech-house: measured energy arc over the first 20s is
// −18.6 → −10.8 dB (low open → mid push → outro peak) — tracks the storyboard's
// energy curve, and the outro 三拍 lands on the track's loudest section.
export const BGM = 'audio/bgm-tech-house.mp3';
// 1s fade-in, 1.7s fade-out, bed held at 0.34 to leave SFX headroom (§4.1).
export const bgmVolume = (f: number) =>
  interpolate(f, [0, 30, 550, 600], [0, 0.34, 0.34, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

// ---- SFX pin table ---------------------------------------------------------
// Volumes: 0.2–0.6 (§4.1); impact-deep-whoosh at 0.55 is the film's SFX peak.
// durationInFrames only where the file exceeds Main's 90f default (riser
// 144f / impact 121f / sparkle 136f — tails must not be truncated).
export type SfxPin = { src: string; from: number; volume: number; durationInFrames?: number };

const SWOOSH = 'audio/sfx/transition/swoosh-quick.mp3';
const SOFT = 'audio/sfx/transition/transition-soft.mp3';
const SNAP = 'audio/sfx/transition/transition-snap.mp3';
const WHOOSH = 'audio/sfx/transition/whoosh-fast.mp3';
const POP = 'audio/sfx/ui/pop.mp3';
const SCAN = 'audio/sfx/data/data-scan.mp3';
const LOCK_Q = 'audio/sfx/mech/lock-quick.mp3';
const LOCK_D = 'audio/sfx/mech/lock-digital.mp3';
const GEAR = 'audio/sfx/mech/gear-lock-metallic.mp3';
const RISER = 'audio/sfx/riser/riser-cine.mp3';
const IMPACT = 'audio/sfx/impact/impact-deep-whoosh.mp3';
const SPARKLE = 'audio/sfx/light/sparkle.mp3';

export const SFX: SfxPin[] = [
  // S1 — title blur-slide: one whoosh at the headline's motion peak (words
  // enter f6; swoosh peak rides f10).
  { src: SWOOSH, from: sfxFrom(SHOT_S1_START + 10, SWOOSH), volume: 0.42 },

  // S1→S2 seam: transition-soft peak lands ON the cut (flash-cut straddles it).
  { src: SOFT, from: sfxFrom(SHOT_S2_START, SOFT), volume: 0.4 },

  // S2 — three rows seat at S2+27/+37/+46 (CUE 14/24/33 + FLIGHT 13).
  // Two near samples alternate so the burst never reads as one looped click;
  // volume ladder 0.40 → 0.28 keeps the repeats from stacking up (§4.2).
  { src: SNAP, from: sfxFrom(SHOT_S2_START + 27, SNAP), volume: 0.4 },
  { src: POP, from: sfxFrom(SHOT_S2_START + 37, POP), volume: 0.34 },
  { src: SNAP, from: sfxFrom(SHOT_S2_START + 46, SNAP), volume: 0.28 },

  // S2→S3 seam.
  { src: SOFT, from: sfxFrom(SHOT_S3_START, SOFT), volume: 0.4 },

  // S3→S4 seam: fast whoosh carries the push into the money shot; its peak
  // lands on the cut, its tail hands off to the scan.
  { src: WHOOSH, from: sfxFrom(SHOT_S4_START, WHOOSH), volume: 0.45 },

  // S4 — scanner: audible window (flat ≈30f + tail ≈10f) is placed over the
  // sweep's payload — line crosses the table at lf57 and fires the four
  // brackets lf63–75 — not over its empty-page lead-in (file is only 60f; the
  // seam whoosh already carries lf0–30).
  { src: SCAN, from: sfxFrom(SHOT_S4_START + 50, SCAN), volume: 0.55 },

  // S4 — bracket locks: first target (lf63) and last target (lf75); the middle
  // two deliberately unvoiced — the burst needs onset, not one noise per event.
  { src: LOCK_Q, from: sfxFrom(SHOT_S4_START + 63, LOCK_Q), volume: 0.45 },
  { src: LOCK_D, from: sfxFrom(SHOT_S4_START + 75, LOCK_D), volume: 0.45 },
  // S4 — SIGNOFF status flip (lf84): metallic gear-lock seals the readout.
  { src: GEAR, from: sfxFrom(SHOT_S4_START + 84, GEAR), volume: 0.5 },

  // S4→S5 seam.
  { src: SOFT, from: sfxFrom(SHOT_S5_START, SOFT), volume: 0.4 },

  // S5 — outro three-beat (§4.3): riser climax at +33 (mid wordmark draw),
  // impact peak exactly on the stamp at +68 (draw end), sparkle at +93 as the
  // tagline/repo settle. 35f / 25f gaps.
  { src: RISER, from: sfxFrom(SHOT_S5_START + 33, RISER), volume: 0.4, durationInFrames: 144 },
  { src: IMPACT, from: sfxFrom(SHOT_S5_START + 68, IMPACT), volume: 0.55, durationInFrames: 121 },
  { src: SPARKLE, from: sfxFrom(SHOT_S5_START + 93, SPARKLE), volume: 0.45, durationInFrames: 136 },
];
