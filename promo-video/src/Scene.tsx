import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { C, FONT, ACCENT, INK3 } from './tokens';

/** Shared "instrument panel" backdrop: dark paper, a faint hairline grid that
 *  reads as a measurement surface, one restrained cobalt bloom low-right, plus
 *  vignette + grain. Used by S1/S2/S5 (the non-page shots). */
export const PanelBg: React.FC<{ push?: number }> = ({ push = 0 }) => {
  const f = useCurrentFrame();
  const breathe = 0.5 + 0.5 * Math.sin(f / 46);
  return (
    <AbsoluteFill style={{ background: C.paper }}>
      {/* hairline grid */}
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${C.lineSoft} 1px, transparent 1px),
                            linear-gradient(90deg, ${C.lineSoft} 1px, transparent 1px)`,
          backgroundSize: '96px 96px',
          backgroundPosition: `${-push * 40}px ${-push * 24}px`,
          opacity: 0.55,
        }}
      />
      {/* single cobalt bloom, low-right, slow breathe — one point light only */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(120% 90% at 82% 108%, ${ACCENT} 0%, rgba(59,130,246,0.16) 34%, rgba(59,130,246,0) 62%)`,
          opacity: 0.28 + 0.06 * breathe,
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(80% 60% at 14% 8%, ${INK3} 0%, rgba(118,125,139,0) 55%)`,
          opacity: 0.06,
        }}
      />
    </AbsoluteFill>
  );
};

/** Screen-space narration caption: cobalt square + sentence-case Inter.
 *  38px (well above the 22px mono info-strip of the template Caption, which the
 *  aesthetic rules flag as a Q11 violation when used as narration). */
export const Caption: React.FC<{ text: string; inAt: number; outAt: number; bottom?: number }> = ({
  text,
  inAt,
  outAt,
  bottom = 64,
}) => {
  const f = useCurrentFrame();
  const inT = interpolate(f, [inAt, inAt + 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const outT = interpolate(f, [outAt - 8, outAt], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const o = inT * outT;
  if (o <= 0) return null;
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        gap: 16,
        fontFamily: FONT.body,
        fontWeight: 500,
        fontSize: 74,
        letterSpacing: '0.005em',
        color: C.ink2,
        opacity: o,
        transform: `translateY(${(1 - inT) * 10}px)`,
        textShadow: '0 2px 18px rgba(0,0,0,0.55)',
        pointerEvents: 'none',
      }}
    >
      <span style={{ width: 9, height: 9, background: ACCENT, display: 'inline-block' }} />
      <span>{text}</span>
    </div>
  );
};
