// Captions layer for Remotion, in the house style.
// Copy into remotion/src/ and render it as the TOP layer of the edit, outside any zoomed or
// scaled container, so captions never follow a camera zoom and their size never drifts.
//
//   import captions from './captions.json';   // written by make_captions.py
//   <Captions captions={captions} />
//
// Style (locked): Departure Mono Regular, white, 38.5 px effective (55 px at 0.7), one line,
// no background, border, stroke or shadow. Position per cue comes from captions.json
// (IN SMALL 540,1262 / IN BIG 540,962 / OUT and FULL 540,1489). Font file expected at
// remotion/public/fonts/DepartureMono-Regular.woff2 (or .otf: change FONT_FILE).

import React from 'react';
import {AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type Caption = {text: string; start: number; end: number; x: number; y: number};

const FONT_FILE = 'fonts/DepartureMono-Regular.woff2';
const FONT_NAME = 'Departure Mono';
const BASE_PX = 55;
const SCALE = 0.7; // 38.5 px effective. Never shrink again to make a phrase fit: split it instead.
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
          transform: `scale(${SCALE})`,
          transformOrigin: `${cue.x}px ${BAND_HEIGHT / 2}px`,
        }}
      >
        <span
          style={{
            fontFamily: `'${FONT_NAME}', monospace`,
            fontSize: BASE_PX,
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
