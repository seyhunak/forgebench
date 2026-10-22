// S4 — scanline-annotate-focus on the REAL compare table (330→475f, 145f)
// THE MONEY SHOT. Grammar = a constant-speed scan line sweeps down the existing
// product page; whichever metric row's bottom edge it crosses, that row gets a
// 4-corner bracket snapping in from 76px outset (one overshoot), then a machine
// label types out. Top status line counts 00/04 → 04/04.
//
// STRICT TWO-COLOR DISCIPLINE (card命门): the page is the Cobalt product UI
// (real 2x screenshot). The scanner is a separate luminous cyan-white layer —
// line, brackets, label chips, status. Viewer instantly separates "the page"
// from "the machine's reading of it". Machine color is NOT the page accent.
//
// The four rows chosen carry the pitch: accuracy up, and the risk metric
// (critical false-match rate) DOWN — the reason risk-aware metrics sell.
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { PageCam, type CamKey } from '../lib/PageCam';
import { ramp, bezier, EASE, tracking, Grain, Vignette } from '../lib/Polish';
import { Caption } from '../Scene';
import { FONT, C, INK3, INK2 } from '../tokens';
import layout from '../live-layout.json';

export const SHOT_S4_START = 330;
export const SHOT_S4_DUR = 145;

const TEX = 'textures/live/compare-full.png';
const PAGE_H = layout.compare.pageH; // 1889
const ROWS = layout.compare.boxes.rows; // 21 rects, page-space CSS px
const TABLE_X = layout.compare.boxes.container.x; // 649
const TABLE_W = layout.compare.boxes.container.w; // 810

const MACH = '#8fe6ff';
const MACH_DIM = 'rgba(143,230,255,0.30)';

// four targets, indexed into layout's rows array — rows[0] is the HEADER row
// (y654.1), so data rows are 1-based: 1=Accuracy, 2=Macro F1,
// 3=Critical False Match Rate, 5=Schema Validity (row 4 = Escalation Recall is
// deliberately NOT flagged — the four chosen carry the pitch).
const TARGETS: { row: number; head: string; tail: string; win: boolean }[] = [
  { row: 1, head: 'ACCURACY', tail: '▲ +0.0452', win: true },
  { row: 2, head: 'MACRO F1', tail: '▲ +0.0442', win: true },
  { row: 3, head: 'CRITICAL FALSE MATCH', tail: '▼ −0.0286', win: true }, // risk DOWN = win
  { row: 5, head: 'SCHEMA VALIDITY', tail: '▲ +0.0667', win: true },
];

// ---- scan timing: constant speed (the machine's eye, no easing) ----
// Line sweeps from above the table to just below the last target (y900), so it
// exits under the final chip instead of continuing across empty page. Speed
// 13.3 px/f → fires land at f63/67/71/75 (4f-clamped, readable as a burst but
// each bracket still reads individually), status flips at ~83 → 62f hold.
const SCAN_FROM = -30;
const SCAN_TO = 900;
const SCAN_A = 6; // frame line is at SCAN_FROM
const SCAN_LEN = 70; // frames to cross — constant speed
const scanY = (f: number) => SCAN_FROM + ((f - SCAN_A) / SCAN_LEN) * (SCAN_TO - SCAN_FROM);
const frameAtY = (y: number) => SCAN_A + ((y - SCAN_FROM) / (SCAN_TO - SCAN_FROM)) * SCAN_LEN;

// fire frame = when line crosses the row's bottom edge; enforce >=4f min gap
const FIRE: number[] = [];
TARGETS.forEach((t, i) => {
  const r = ROWS[t.row];
  const ft = frameAtY(r.y + r.h);
  const min = i === 0 ? 0 : FIRE[i - 1] + 4;
  FIRE.push(Math.max(ft, min));
});
const LAST_FIRE = FIRE[FIRE.length - 1];

// The 4 target rows span page-y 691.4 (Accuracy top) .. 885.0 (Schema bottom).
// Center the camera on their real midpoint (~788), not the table's vertical
// middle — otherwise the zoomed viewport crops the table's top rows and clips
// the "Critical False Match Rate" label, which is the money metric's name.
const TARGET_TOP = ROWS[1].y; // 691.4 (Accuracy)
const TARGET_BOTTOM = ROWS[5].y + ROWS[5].h; // 885.0 (Schema, the last target)
const FOCUS_Y = (TARGET_TOP + TARGET_BOTTOM) / 2; // ~788
// camera: extremely slow push (1.16→1.19). Kept FLAT (no rotX/rotY) so the
// page-space brackets/labels stay locked to the exact table pixels they annotate.
const KEYS: CamKey[] = [
  { frame: 0, cx: TABLE_X + TABLE_W / 2, cy: FOCUS_Y, zoom: 1.16 },
  { frame: SHOT_S4_DUR - 4, cx: TABLE_X + TABLE_W / 2, cy: FOCUS_Y - 8, zoom: 1.19 },
];
// Labels are COMPACT NUMERAL-ONLY delta chips placed in the empty right-hand page
// margin (x≈1460→1880 at this framing — ~420px of blank surface beside the table).
// Anchoring long "METRIC NAME −0.0286" chips to the left band clipped them off the
// frame's left edge (the visible page-band at zoom 1.16 starts at x≈226, but a
// 600px chip right-anchored at the table's left edge started at x≈29 → cut off).
// The metric name stays inside the bracketed row, so the chip only has to carry
// the value; the arrow states direction, green states "this is the win".
const LABEL_X = TABLE_X + TABLE_W + 20; // page-space; just right of the table's right edge
const LABEL_MAX_W = 400; // stays inside the right margin, off the frame's right edge

const bracketSpring = bezier(0.34, 1.4, 0.5, 1); // one visible overshoot

const Bracket: React.FC<{ x: number; y: number; w: number; h: number; ft: number }> = ({ x, y, w, h, ft }) => {
  const f = useCurrentFrame();
  if (f < ft) return null;
  const s = bracketSpring(ramp(f, ft, 15, EASE.linear));
  const outset = 76;
  const off = outset * (1 - s);
  const arm = 34 - 8 * ramp(f, ft + 3, 8, EASE.out); // 40→26, 3f later
  const focusFlash = f >= ft + 3 && f < ft + 16 ? ramp(f, ft + 3, 3, EASE.out) * (1 - ramp(f, ft + 6, 10, EASE.out)) : 0;
  const L = (st: React.CSSProperties): React.CSSProperties => ({ position: 'absolute', background: MACH, boxShadow: `0 0 8px ${MACH}`, ...st });
  const corners: React.CSSProperties[] = [
    L({ left: x - off, top: y - off, width: arm, height: 3.5, transformOrigin: 'left top' }),
    L({ left: x - off, top: y - off, width: 3.5, height: arm, transformOrigin: 'left top' }),
    L({ left: x + w + off - arm, top: y - off, width: arm, height: 3.5 }),
    L({ left: x + w + off - 3.5, top: y - off, width: 3.5, height: arm }),
    L({ left: x - off, top: y + h + off - 3.5, width: arm, height: 3.5 }),
    L({ left: x - off, top: y + h + off - arm, width: 3.5, height: arm }),
    L({ left: x + w + off - arm, top: y + h + off - 3.5, width: arm, height: 3.5 }),
    L({ left: x + w + off - 3.5, top: y + h + off - arm, width: 3.5, height: arm }),
  ];
  return (
    <>
      {focusFlash > 0 && (
        <div style={{ position: 'absolute', left: x, top: y, width: w, height: h, background: MACH, opacity: focusFlash * 0.1, border: `2px solid ${MACH}` }} />
      )}
      {corners.map((st, i) => (
        <div key={i} style={st} />
      ))}
    </>
  );
};

const MachineLabel: React.FC<{ left: number; y: number; h: number; ft: number; value: string; win: boolean }> = ({ left, y, h, ft, value, win }) => {
  const f = useCurrentFrame();
  const at = ft + 5;
  if (f < at) return null;
  const nChars = Math.max(0, Math.round((f - at) * 1.8));
  const shown = value.slice(0, nChars);
  const done = nChars >= value.length;
  const wipe = ramp(f, at, 6, EASE.out);
  const up = (1 - ramp(f, at, 8, EASE.out)) * 8;
  return (
    <div
      style={{
        position: 'absolute',
        left,
        top: y + h / 2 - 16 - up, // vertically centered on its row (chip height 32 + 6px padding)
        clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)`,
        background: MACH,
        color: win ? '#06281c' : '#28060e',
        fontFamily: FONT.mono,
        fontSize: 32,
        fontWeight: 700,
        letterSpacing: '0.02em',
        lineHeight: 1,
        padding: '3px 10px', // total 38px ≤ 38.7px row pitch — consecutive rows' chips never touch
        borderRadius: 4,
        whiteSpace: 'pre',
        maxWidth: LABEL_MAX_W,
        overflow: 'hidden',
        boxShadow: `0 0 22px ${MACH_DIM}`,
      }}
    >
      {shown}
      {!done && <span style={{ opacity: 0.9 }}>▍</span>}
    </div>
  );
};

export const ShotS4: React.FC = () => {
  const lf = useCurrentFrame();
  const y = scanY(lf);
  const lineVisible = lf >= SCAN_A && lf <= SCAN_A + SCAN_LEN + 6;
  const lineOpacity = lf < SCAN_A ? 0 : 1 - ramp(lf, SCAN_A + SCAN_LEN, 6, EASE.out);
  const fired = FIRE.filter((ft) => lf >= ft).length;
  const statusDone = lf > LAST_FIRE + 8;
  const vign = ramp(lf, 0, 18, EASE.out);

  // page-space children: scan line + brackets + labels
  const overlays = (
    <>
      {TARGETS.map((t, i) => (
        <Bracket key={`b${i}`} x={ROWS[t.row].x} y={ROWS[t.row].y} w={ROWS[t.row].w} h={ROWS[t.row].h} ft={FIRE[i]} />
      ))}
      {TARGETS.map((t, i) => (
        <MachineLabel
          key={`l${i}`}
          left={LABEL_X}
          y={ROWS[t.row].y}
          h={ROWS[t.row].h}
          ft={FIRE[i]}
          value={t.tail}
          win={t.win}
        />
      ))}
      {lineVisible && (
        <div style={{ position: 'absolute', left: 0, width: 1920, top: y, opacity: lineOpacity }}>
          {/* 140px trail above the line */}
          <div style={{ position: 'absolute', left: 0, width: '100%', bottom: 0, height: 140, background: `linear-gradient(180deg, transparent, ${MACH_DIM})` }} />
          <div style={{ position: 'absolute', left: 0, width: '100%', height: 3, background: MACH, boxShadow: `0 0 16px ${MACH}` }} />
        </div>
      )}
    </>
  );

  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <PageCam src={TEX} pageH={PAGE_H} keys={KEYS} frame={SHOT_S4_START + lf}>
        {overlays}
      </PageCam>

      {/* status line — screen space, top-left. A soft left-edge scrim lifts it
          clear of the app's own nav rail underneath (which is page content). */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: 760,
          height: 150,
          background:
            'linear-gradient(105deg, rgba(13,15,20,0.92) 0%, rgba(13,15,20,0.72) 45%, rgba(13,15,20,0) 100%)',
          opacity: ramp(lf, 0, 10, EASE.out),
          pointerEvents: 'none',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 60,
          top: 44,
          fontFamily: FONT.mono,
          fontSize: 22,
          letterSpacing: tracking(22, true),
          color: statusDone ? MACH : C.ink2,
          display: 'flex',
          alignItems: 'center',
          gap: 18,
          opacity: ramp(lf, 0, 10, EASE.out),
        }}
      >
        <span style={{ width: 9, height: 9, background: statusDone ? MACH : INK3, boxShadow: statusDone ? `0 0 10px ${MACH}` : undefined }} />
        {statusDone ? 'SIGNOFF · RISK DOWN' : 'SCANNING'}
        <span style={{ color: INK3 }}>
          {String(fired).padStart(2, '0')} / {String(TARGETS.length).padStart(2, '0')}
        </span>
        {/* progress bar */}
        <span style={{ display: 'inline-block', width: 140, height: 3, background: C.line, position: 'relative', top: 2 }}>
          <span style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${ramp(lf, SCAN_A, SCAN_LEN, EASE.linear) * 100}%`, background: statusDone ? MACH : INK2 }} />
        </span>
      </div>

      {/* bottom scrim — keeps the caption legible where the table's lower rows
          pass beneath it (page content, not our layer) */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: 260,
          background: 'linear-gradient(180deg, rgba(13,15,20,0) 0%, rgba(13,15,20,0.78) 55%, rgba(13,15,20,0.9) 100%)',
          opacity: ramp(lf, 20, 12, EASE.out),
          pointerEvents: 'none',
        }}
      />
      <Vignette strength={0.32 * vign} />
      <Grain opacity={0.045} />
      <Caption
        text="Pin a baseline. Read the delta. Ship only what improves the risk metric."
        inAt={30}
        outAt={SHOT_S4_DUR - 8}
        bottom={72}
      />
    </AbsoluteFill>
  );
};
