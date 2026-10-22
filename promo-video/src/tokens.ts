// ForgeBench "Instrument panel" tokens — extracted verbatim from
// src/forgebench/static/style.css. Product CSS is the single source of truth;
// this file only converts hex into the named roles the shots reference.
import { EASE } from './lib/Polish';

export const C = {
  // Surfaces (dark Cobalt product)
  paper: '#0d0f14',
  surface: '#14171e',
  surface2: '#191d25',
  surface3: '#20242e',
  line: '#2a2f3a',
  lineSoft: 'rgba(255,255,255,0.06)',

  // Ink
  ink: '#eef1f6',
  ink2: '#a6adba',
} as const;

// Flat ink aliases (named exports for shot imports)
export const INK = C.ink;
export const INK2 = C.ink2;

// Accurate ink3 + accent + signals (oklch → hex, measured off product CSS)
export const INK3 = '#767d8b';
export const ACCENT = '#3b82f6'; // oklch(63% .19 256) — cobalt
export const ACCENT_HI = '#6aa5ff'; // oklch(72% .17 256) — focus
export const SUCCESS = '#4ade9c'; // oklch(74% .16 152)
export const DANGER = '#e56a45'; // oklch(67% .2 25)
export const INFO = '#66b5e8'; // oklch(71% .13 220)

// Machine-vision color — deliberately NOT the page accent, so the scanner
// reads as a separate analytical layer over the Cobalt product (strict
// two-color discipline from the scanline card).
export const MACHINE = '#7fdfff'; // luminous cyan-white
export const MACHINE_DIM = 'rgba(127,223,255,0.35)';

export const FONT = {
  display: '"Space Grotesk", "Inter", system-ui, sans-serif',
  body: '"Inter", system-ui, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, Menlo, monospace',
} as const;

// Motion preset = 专业信赖 (enterprise / B2B / fintech): decisive in, soft stop,
// no overshoot on fades. Main move ~21f.
export const MOTION = {
  ease: EASE.out, // quint-out level
  easeSmooth: EASE.smooth,
  dur: 21,
  stagger: 4,
} as const;
