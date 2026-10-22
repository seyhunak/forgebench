// S2 — row-embed use-case panel (88→195f, 107f)
// NOTE: this is a *designed* panel, not a product replica. The product page
// replicas (S3/S4) use real 2x screenshots; this mid-section is pitch framing,
// so a composed instrument-panel card is correct.
//
// Grammar = row-embed: three use-case rows drop in from above, rotateX flattens
// (16deg→0) as they near the slot, a slot patch + dashed frame holds the gap,
// and the row's bottom edge lights a 2px cobalt seam on the frame it seats.
// Cues accelerate (10→7f gap) so the last row lands on a strong beat.
// Slot patch = panel surface color; if it were absent the baked page texture
// would bleed through and the row would read as a ghost (Q1 rule).
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { ramp, bezier, EASE, tracking, softShadow, Grain, Vignette } from '../lib/Polish';
import { PanelBg } from '../Scene';
import { FONT, ACCENT, INK, INK2, INK3, C } from '../tokens';

export const SHOT_S2_START = 88;
export const SHOT_S2_DUR = 107;

const ROWS = [
  { tag: 'USE CASE 01', label: 'Prompt & fine-tune A/B validation', meta: 'Δ vs baseline' },
  { tag: 'USE CASE 02', label: 'CI regression gates on every PR', meta: 'pass / fail' },
  { tag: 'USE CASE 03', label: 'Risk-aware metrics — critical false-match rate', meta: 'weighted' },
];

// accelerating cues; flight 13f; last seats at +46f (CUE 33 + FLIGHT 13), seam settles ~65f → 30f+ hold
const CUE = [14, 24, 33];
const FLIGHT = 13;
const ROW_H = 132;
const GAP = 20;
const flyEase = bezier(0.5, 0, 0.8, 0.75); // still carrying speed at the end → seats hard

const PANEL_W = 1180;
const PANEL_X = (1920 - PANEL_W) / 2;
const PANEL_TOP = 250;

const Row: React.FC<{ i: number; y: number }> = ({ i, y }) => {
  const f = useCurrentFrame();
  const c = CUE[i];
  const t = ramp(f, c, FLIGHT, flyEase);
  const air = 1 - t;
  // seat + 4f press-bounce back to 1 (the "click")
  const seat = ramp(f, c + FLIGHT, 4, EASE.out);
  const press = 1 - 0.055 * seat * (1 - ramp(f, c + FLIGHT + 4, 6, EASE.out));
  const scale = (1.06 - 0.065 * t) * press;
  const seated = f >= c + FLIGHT;
  const r = ROWS[i];

  return (
    <div style={{ position: 'absolute', left: 40, top: y, width: PANEL_W - 80, height: ROW_H }}>
      {/* slot frame holds the gap before the row seats (dashed guide) */}
      <div
        style={{
          position: 'absolute',
          inset: -2,
          border: `1px dashed ${C.line}`,
          borderRadius: 10,
          opacity: seated ? 0 : 0.4,
        }}
      />
      {/* contact shadow, tightens as the row nears its slot */}
      <div
        style={{
          position: 'absolute',
          left: 8,
          right: 8,
          bottom: -6,
          height: 24,
          background: 'radial-gradient(ellipse 50% 100% at 50% 0%, rgba(0,0,0,0.55), rgba(0,0,0,0))',
          opacity: (1 - t) * (0.35 + 0.65 * t),
          filter: `blur(${(1 - t) * 8}px)`,
        }}
      />
      {/* flying body */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `linear-gradient(180deg, ${C.surface3} 0%, ${C.surface2} 100%)`,
          border: `1px solid ${C.line}`,
          borderRadius: 10,
          opacity: f < c ? 0 : 1,
          transform: `perspective(900px) translateY(${-120 * air}px) rotateX(${16 * air}deg) scale(${scale})`,
          transformOrigin: '50% 100%',
          boxShadow: softShadow(3, { strength: 0.5 }),
          display: 'flex',
          alignItems: 'center',
          padding: '0 34px',
          gap: 28,
        }}
      >
        {/* index chip */}
        <div
          style={{
            fontFamily: FONT.mono,
            fontSize: 46,
            letterSpacing: tracking(46, true),
            color: ACCENT,
            border: `1px solid rgba(59,130,246,0.4)`,
            borderRadius: 6,
            padding: '8px 12px',
            whiteSpace: 'nowrap',
          }}
        >
          {r.tag}
        </div>
        <div style={{ fontFamily: FONT.display, fontSize: 33, fontWeight: 500, color: INK, letterSpacing: '-0.01em', flex: 1 }}>
          {r.label}
        </div>
        <div style={{ fontFamily: FONT.mono, fontSize: 46, letterSpacing: '0.08em', color: INK3, whiteSpace: 'nowrap' }}>
          {r.meta}
        </div>
        {/* cobalt seam lights the bottom edge the instant it seats */}
        <div
          style={{
            position: 'absolute',
            left: '50%',
            bottom: -1,
            height: 2,
            width: `${ramp(f, c + FLIGHT, 5, EASE.out) * 100}%`,
            transform: 'translateX(-50%)',
            opacity: seated ? 1 - ramp(f, c + FLIGHT + 5, 14, EASE.out) : 0,
            background: `linear-gradient(90deg, transparent, ${ACCENT} 18%, ${ACCENT} 82%, transparent)`,
            boxShadow: `0 0 14px ${ACCENT}`,
          }}
        />
      </div>
    </div>
  );
};

export const ShotS2: React.FC = () => {
  const f = useCurrentFrame();
  // very slow push + downward tilt of the whole panel, parallel to the row rain
  const push = ramp(f, 0, SHOT_S2_DUR, EASE.smooth);
  const camTilt = 30 * push;
  const zoom = 1 + 0.05 * push;
  // panel + header rise in over the first 14f
  const panelIn = ramp(f, 0, 16, EASE.out);

  return (
    <AbsoluteFill>
      <PanelBg push={push} />
      <Vignette strength={0.55} />
      <AbsoluteFill
        style={{
          transform: `translateY(${camTilt}px) scale(${zoom})`,
          transformOrigin: '50% 42%',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: PANEL_X,
            top: PANEL_TOP,
            width: PANEL_W,
            height: 98 + ROWS.length * ROW_H + (ROWS.length - 1) * GAP + 30,
            background: `linear-gradient(180deg, rgba(25,29,37,0.92), rgba(20,23,30,0.92))`,
            border: `1px solid ${C.line}`,
            borderRadius: 16,
            boxShadow: softShadow(6, { strength: 0.6 }),
            opacity: panelIn,
            transform: `translateY(${(1 - panelIn) * 24}px)`,
          }}
        >
          {/* panel header */}
          <div
            style={{
              padding: '30px 40px 22px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: `1px solid ${C.line}`,
            }}
          >
            <div style={{ fontFamily: FONT.mono, fontSize: 44, letterSpacing: tracking(44, true), color: INK2, display: 'flex', alignItems: 'center', gap: 14 }}>
              <span style={{ width: 8, height: 8, background: ACCENT }} />
              WHAT USE CASES RUN HERE
            </div>
            <div style={{ fontFamily: FONT.mono, fontSize: 44, letterSpacing: '0.1em', color: INK3 }}>FORGEBENCH</div>
          </div>
          {ROWS.map((_, i) => (
            <Row key={i} i={i} y={98 + i * (ROW_H + GAP)} />
          ))}
        </div>
      </AbsoluteFill>
      <Grain opacity={0.05} />
    </AbsoluteFill>
  );
};
