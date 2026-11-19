// Captions layer for Remotion.
// Copy into remotion/src/ and render it as the TOP layer of the edit, outside any zoomed or
// scaled container, so captions never follow a camera zoom and their size never drifts.
//
//   import captions from './captions.json';   // written by make_captions.py
//   <Captions captions={captions} />
//
// Default look: Departure Mono (a free digital-style font), white, one line, no box.
// Swap the font by changing FONT_FILE and FONT_NAME; change the size with FONT_PX.
// Keep one font and one size for the whole video: only the position changes per layout.
// Position per cue comes from captions.json (IN SMALL 540,1262 / IN BIG 540,962 /
// OUT and FULL 540,1489).

import React from 'react';
import {AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type Caption = {text: string; start: number; end: number; x: number; y: number};

const FONT_FILE = 'fonts/DepartureMono-Regular.woff2';
const FONT_NAME = 'Departure Mono';
const FONT_PX = 40; // one size for the whole video. Never shrink a phrase to fit: split it instead.
const BAND_HEIGHT = 72;

let fontPromise: Promise<void> | null = null;
const loadFont = () => {
  if (!fontPromise) {
    const face = new FontFace(FONT_NAME, `url(${staticFile(FONT_FILE)})`);
    fontPromise = face.load().then((f) => {
      document.fonts.add(f);
    });
  }
  return fontPromise;
};

export const Captions: React.FC<{captions: Caption[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const [handle] = React.useState(() => delayRender('Loading caption font'));
  React.useEffect(() => {
    loadFont().then(() => continueRender(handle)).catch((err) => {
      console.error('Caption font failed to load', err);
      continueRender(handle);
    });
  }, [handle]);

  const t = frame / fps;
  // Cues never overlap, so at most one is on screen: never more than three words visible.
  const cue = captions.find((c) => t >= c.start && t < c.end);
  if (!cue) return null;

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          width: 1080,
          top: cue.y - BAND_HEIGHT / 2,
          height: BAND_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span
          style={{
            fontFamily: `'${FONT_NAME}', monospace`,
            fontSize: FONT_PX,
            lineHeight: 1,
            color: '#FFFFFF',
            whiteSpace: 'nowrap',
          }}
        >
          {cue.text}
        </span>
      </div>
    </AbsoluteFill>
  );
};
