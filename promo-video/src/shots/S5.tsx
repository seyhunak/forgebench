// S5 — FORGEBENCH wordmark letterspace-materialize (475→600f, 125f)
// Grammar = every letter's skeleton strokes draw in PARALLEL — same start
// frame, same end frame (pathLength normalized so unequal-length strokes still
// finish together). No per-letter stagger (that reads as typewriter; this is one
// ceremonial crystallization). Then a hold ≥30f.
//
// Glyph provenance: f,o,r,e,c,h reused from the letterspace-materialize demo
// (video-shotcraft lowercase skeleton, 64-box: baseline y59 / x-height y22 /
// ascender y5). g,b,n hand-drawn to match — circle bowls + round caps. "b" is
// the mirror of the demo's "d"; "g" adds a descender tail; "n" is an arch.
// Any letter missing a stroke would read as a broken wordmark, so each glyph is
// verified against a still before render.
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { ramp, bezier, EASE, tracking, Grain, Vignette } from '../lib/Polish';
import { PanelBg } from '../Scene';
import { FONT, ACCENT, INK2, INK3 } from '../tokens';

export const SHOT_S5_START = 475;
export const SHOT_S5_DUR = 125;

// 64-height viewbox per glyph; baseline y59, x-height y22, ascender y5, descender y70
const GLYPHS: Record<string, { w: number; d: string }> = {
  f: { w: 26, d: 'M 23 7 C 17 4, 11 6, 11 14 L 11 59 M 3 22 L 22 22' },
  o: { w: 46, d: 'M 23 22 A 18.5 18.5 0 0 0 23 59 A 18.5 18.5 0 0 0 23 22' },
  r: { w: 28, d: 'M 5 22 L 5 59 M 5 38 C 5 27, 13 22, 24 23' },
  // g — bowl (mirror of demo's 'a' bowl) + descender with a left hook tail
  g: { w: 46, d: 'M 41.5 40.5 A 18.5 18.5 0 0 0 4.5 40.5 A 18.5 18.5 0 0 0 41.5 40.5 M 41.5 22 L 41.5 70 C 41.5 77, 33 79, 26 76' },
  e: { w: 46, d: 'M 4.5 40.5 L 41.5 40.5 A 18.5 18.5 0 1 0 37.2 52.4' },
  // b — mirror of the demo's 'd' (stem on the left, bowl to its right)
  b: { w: 46, d: 'M 4.5 5 L 4.5 59 M 4.5 40.5 A 18.5 18.5 0 0 1 41.5 40.5 A 18.5 18.5 0 0 1 4.5 40.5' },
  n: { w: 41, d: 'M 5 22 L 5 59 M 5 40 C 5 29, 13 22, 21 22 C 30 22, 36 29, 36 40 L 36 59' },
  c: { w: 42, d: 'M 37.2 28.6 A 18.5 18.5 0 1 0 37.2 52.4' },
  h: { w: 41, d: 'M 5 5 L 5 59 M 5 38 C 5 27, 12 22, 20.5 22 C 30 22, 36 27, 36 37 L 36 59' },
};

const WORD = 'forgebench';
const GLYPH_SCALE = 1.5;
const GLYPH_H = 64 * GLYPH_SCALE;
const TRACK = 34; // large tracking = this card's identity
const START = 16; // all letters start together
const DUR = 52; // all letters finish together (pathLength normalized)
const strokeEase = bezier(0.5, 0, 0.3, 1); // slow start, fast middle, soft finish

const Word: React.FC<{ e: number; glow: number }> = ({ e, glow }) => (
  <div style={{ display: 'flex', gap: TRACK, alignItems: 'center' }}>
    {WORD.split('').map((ch, li) => {
      const g = GLYPHS[ch];
      return (
        <svg
          key={li}
          width={g.w * GLYPH_SCALE}
          height={GLYPH_H}
          viewBox={`0 0 ${g.w} 64`}
          style={{ overflow: 'visible', display: 'block' }}
        >
          {e > 0 && (
            <path
              d={g.d}
              fill="none"
              stroke="#eef1f6"
              strokeWidth={5.5 / GLYPH_SCALE}
              strokeLinecap="round"
              strokeLinejoin="round"
              pathLength={1}
              strokeDasharray={1}
              strokeDashoffset={1 - e}
              style={{ filter: `drop-shadow(0 0 ${(5 + glow * 10) / GLYPH_SCALE}px rgba(59,130,246,${0.28 + glow * 0.36}))` }}
            />
          )}
        </svg>
      );
    })}
  </div>
);

export const ShotS5: React.FC = () => {
  const f = useCurrentFrame();
  const e = ramp(f, START, DUR, strokeEase); // one shared progress → parallel draw
  const rise = ramp(f, START + DUR * 0.7, DUR * 0.3, EASE.swift);
  const fall = 1 - ramp(f, START + DUR, 14, EASE.out);
  const glow = e >= 1 ? fall : rise;
  const push = ramp(f, 0, SHOT_S5_DUR, EASE.smooth);

  const tagIn = ramp(f, START + DUR + 6, 20, EASE.out);
  const repoIn = ramp(f, START + DUR + 16, 18, EASE.out);

  return (
    <AbsoluteFill>
      <PanelBg push={push} />
      <Vignette strength={0.6} />
      <AbsoluteFill style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 0 }}>
        <Word e={e} glow={glow} />
        <div
          style={{
            marginTop: 56,
            fontFamily: FONT.body,
            fontSize: 46,
            fontWeight: 400,
            color: INK2,
            opacity: tagIn,
            transform: `translateY(${(1 - tagIn) * 14}px)`,
            letterSpacing: '0.005em',
          }}
        >
          Measure what customization actually changed.
        </div>
        <div
          style={{
            marginTop: 30,
            fontFamily: FONT.mono,
            fontSize: 46,
            letterSpacing: tracking(46, true),
            color: INK3,
            opacity: repoIn,
            transform: `translateY(${(1 - repoIn) * 10}px)`,
            display: 'flex',
            alignItems: 'center',
            gap: 14,
          }}
        >
          <span style={{ width: 8, height: 8, background: ACCENT, display: 'inline-block' }} />
          GITHUB.COM/SEYHUNAK/FORGEBENCH
        </div>
      </AbsoluteFill>
      <Grain opacity={0.05} />
    </AbsoluteFill>
  );
};
