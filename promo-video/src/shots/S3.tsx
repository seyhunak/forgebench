// S3 — report modal PageCam glide (195→330f, 135f)
// Grammar = camera move only. Subject is the REAL 2x screenshot of the
// run-detail modal (report-full.png); PageCam renders it at CSS size via the
// zoom technique so text stays crisp. Slight oblique tilt at entry, straightens
// + pushes toward the metric strip, ends dead-flat on a hold.
// PageCam reads absolute comp frame internally, so we pass it the Sequence's
// restored absolute frame (SHOT_S3_START + local).
import React from 'react';
import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { PageCam, type CamKey } from '../lib/PageCam';
import { ramp, EASE, Grain, Vignette } from '../lib/Polish';
import { Caption } from '../Scene';
import { C } from '../tokens';

export const SHOT_S3_START = 195;
export const SHOT_S3_DUR = 135;

const TEX = 'textures/live/report-full.png'; // staticFile path under public/
const PAGE_H = 1080; // viewport shot

const KEYS: CamKey[] = [
  { frame: 0, cx: 940, cy: 560, zoom: 1.26, rotX: 5, rotY: -3.5, persp: 1500 },
  { frame: 96, cx: 960, cy: 548, zoom: 1.0, rotX: 0, rotY: 0, persp: 1600 },
];

export const ShotS3: React.FC = () => {
  const lf = useCurrentFrame();
  const vign = ramp(lf, 0, 20, EASE.out);

  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <PageCam src={TEX} pageH={PAGE_H} keys={KEYS} frame={SHOT_S3_START + lf} />
      <Vignette strength={0.4 * vign} />
      <Grain opacity={0.045} />
      <Caption
        text="Self-describing run artifacts — report, predictions, traces"
        inAt={26}
        outAt={SHOT_S3_DUR - 6}
      />
    </AbsoluteFill>
  );
};
