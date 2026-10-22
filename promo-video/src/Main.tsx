// Main — 600-frame (20.0s) ForgeBench pitch timeline.
// Shot boundaries are the single source of truth (SHOTS below). Each shot gets a
// flash-cut seam at its start so no two shots are joined by a bare cut.
//
// AUDIO (stage 6): all pin math lives in audio.ts — SFX pins are expressions
// relative to each shot's start frame (retiming a shot never desyncs its
// sounds), peak-aligned through sfxFrom(). Main only renders the table. BGM is
// one bed with a `bgm` inputProp gate so we ship a with-BGM and a no-BGM render
// from the same timeline.
import React from 'react';
import { AbsoluteFill, Sequence, Audio, staticFile } from 'remotion';
import { FlashCut } from './lib/FlashCut';
import { ShotS1, SHOT_S1_START, SHOT_S1_DUR } from './shots/S1';
import { ShotS2, SHOT_S2_START, SHOT_S2_DUR } from './shots/S2';
import { ShotS3, SHOT_S3_START, SHOT_S3_DUR } from './shots/S3';
import { ShotS4, SHOT_S4_START, SHOT_S4_DUR } from './shots/S4';
import { ShotS5, SHOT_S5_START, SHOT_S5_DUR } from './shots/S5';
import { SFX, BGM, bgmVolume, hasAudio } from './audio';

export type MainProps = { bgm: boolean };

// ---- shot boundaries (single source of truth) ----
export const SHOTS = [
  { id: 's1', start: SHOT_S1_START, dur: SHOT_S1_DUR, Comp: ShotS1 },
  { id: 's2', start: SHOT_S2_START, dur: SHOT_S2_DUR, Comp: ShotS2 },
  { id: 's3', start: SHOT_S3_START, dur: SHOT_S3_DUR, Comp: ShotS3 },
  { id: 's4', start: SHOT_S4_START, dur: SHOT_S4_DUR, Comp: ShotS4 },
  { id: 's5', start: SHOT_S5_START, dur: SHOT_S5_DUR, Comp: ShotS5 },
] as const;

// ---- SFX pins (stage 6): audio.ts computes each pin's absolute frame as
// shotStart + rel − peakLag − outputOffset; Main just renders the table. ----

export const Main: React.FC<MainProps> = ({ bgm }) => {
  return (
    <AbsoluteFill style={{ background: '#0d0f14' }}>
      {SHOTS.map(({ id, start, dur, Comp }) => (
        <Sequence key={id} from={start} durationInFrames={dur} name={id}>
          <Comp />
        </Sequence>
      ))}

      {/* flash-cut seams: a short bright bloom straddles each hard cut */}
      {SHOTS.filter(({ id }) => id !== 's1' && id !== 's2').map(({ id, start }) => (
        <Sequence key={`fc-${id}`} from={start - 4} durationInFrames={10} name={`fc-${id}`}>
          <FlashCut duration={10} />
        </Sequence>
      ))}

      {/* sound design (stage 6): peak-aligned pins + bed BGM with envelope */}
      {hasAudio &&
        SFX.map((s, i) => (
          <Sequence
            key={`sfx-${i}`}
            from={s.from}
            durationInFrames={s.durationInFrames ?? 90}
            name={`sfx-${i}`}
          >
            <Audio src={staticFile(s.src)} volume={s.volume} />
          </Sequence>
        ))}
      {hasAudio && bgm && <Audio src={staticFile(BGM)} volume={bgmVolume} />}
    </AbsoluteFill>
  );
};
