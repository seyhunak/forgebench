import React from 'react';
import { Composition } from 'remotion';
import { Main } from './Main';

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const DURATION = 600; // 20.0s @30fps — hard constraint

export const Root: React.FC = () => (
  <Composition
    id="ForgeBench20s"
    component={Main}
    durationInFrames={DURATION}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
    defaultProps={{ bgm: true }}
  />
);
