// S1 — blur-slide headline (0→88f)
// Grammar: word-by-word reveal. y + blur + opacity all ride ONE progress p with
// ONE easing, so words surface "out of defocus" rather than slide-then-fade.
// Sub starts before the headline finishes (26f overlap = one breath, not two beats).
// Hold: last word settles at f58 → ≥30f of true stillness (R1).
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { ramp, EASE, tracking, Grain, Vignette } from '../lib/Polish';
import { PanelBg } from '../Scene';
import { FONT, ACCENT, INK2, INK3 } from '../tokens';

const KICKER = 'DOMAIN EVAL HARNESS';
const L1 = ['Measure', 'domain', 'adaptation,'];
const L2 = ['not', 'just', 'model', 'intelligence.'];
const SUB = 'ForgeBench · reproducible, provider-agnostic evaluation';
const ACCENT_WORD = 'domain';

type WordCfg = { start: number; dur: number; dy: number; b: number };

const Word: React.FC<{ w: string; cfg: WordCfg; accent?: boolean }> = ({ w, cfg, accent }) => {
  const f = useCurrentFrame();
  const p = ramp(f, cfg.start, cfg.dur, EASE.out); // single progress → all channels
  return (
    <span
      style={{
        display: 'inline-block',
        opacity: p,
        transform: `translateY(${(1 - p) * cfg.dy}px)`,
        filter: `blur(${(1 - p) * cfg.b}px)`,
        color: accent ? ACCENT : undefined,
        willChange: 'transform, filter, opacity',
      }}
    >
      {w}
    </span>
  );
};

export const SHOT_S1_START = 0;
export const SHOT_S1_DUR = 88;

export const ShotS1: React.FC = () => {
  const f = useCurrentFrame();
  const kp = ramp(f, 2, 14, EASE.out);
  const push = ramp(f, 0, SHOT_S1_DUR, EASE.smooth); // imperceptible bg drift

  const H = { dy: 56, b: 17 };
  const S = { dy: 24, b: 9 };
  // L1: 3 words, start 6, gap 4, dur 22 → last settles 36
  const l1cfg = (i: number): WordCfg => ({ start: 6 + i * 4, dur: 22, ...H });
  // L2: breath, 4 words, start 26, gap 4, dur 22; "intelligence." longer → settles 58
  const l2cfg = (i: number): WordCfg => ({
    start: 26 + i * 4,
    dur: i === L2.length - 1 ? 26 : 22,
    ...H,
  });
  // Sub: 8 words, start 32 (overlaps L2 by 26f), gap 2, dur 18 → settles 56
  const subWords = SUB.split(' ');
  const scfg = (i: number): WordCfg => ({ start: 32 + i * 2, dur: 18, ...S });

  return (
    <AbsoluteFill>
      <PanelBg push={push} />
      <Vignette strength={0.55} />
      <AbsoluteFill style={{ padding: '150px 168px', fontFamily: FONT.display }}>
        <div
          style={{
            fontFamily: FONT.mono,
            fontSize: 44,
            letterSpacing: tracking(44, true),
            color: INK3,
            opacity: kp,
            transform: `translateY(${(1 - kp) * 8}px)`,
            marginBottom: 40,
            display: 'flex',
            alignItems: 'center',
            gap: 14,
          }}
        >
          <span style={{ width: 8, height: 8, background: ACCENT, display: 'inline-block' }} />
          {KICKER}
        </div>

        <div style={{ fontSize: 116, fontWeight: 500, lineHeight: 1.04, letterSpacing: '-0.02em', color: '#f3f6fb' }}>
          <div style={{ display: 'flex', gap: '0.3em' }}>
            {L1.map((w, i) => (
              <Word key={i} w={w} cfg={l1cfg(i)} accent={w === 'domain' || w === 'adaptation'} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.3em', marginTop: 8 }}>
            {L2.map((w, i) => (
              <Word key={i} w={w} cfg={l2cfg(i)} />
            ))}
          </div>
        </div>

        <div
          style={{
            marginTop: 44,
            fontFamily: FONT.body,
            fontSize: 34,
            fontWeight: 400,
            color: INK2,
            display: 'flex',
            gap: '0.32em',
            alignItems: 'baseline',
          }}
        >
          {subWords.map((w, i) => (
            <Word key={i} w={w} cfg={scfg(i)} />
          ))}
        </div>
      </AbsoluteFill>
      <Grain opacity={0.05} />
    </AbsoluteFill>
  );
};
