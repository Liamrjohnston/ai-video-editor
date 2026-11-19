# AI Video Editor

Edit talking-head Reels with Claude Code. No editing app. You drop in raw footage, tell Claude to edit it, and the skills take it to a finished 9:16 video: a tight cut, a consistent layout with captions, sound effects on everything that moves, and motion graphics built from real logos and screenshots.

## The skills

The four skills from the video, with captions split out of style so they're easy to find.

| Skill | What it does | Why it exists |
| --- | --- | --- |
| **cut** | Finds your best take of every line and cuts out all the dead air, down to the frame. Checks every join for picture jumps, mic dropouts and uneven voice. | AI cuts tend to chop the end off words or slice a breath in half and leave a weird noise. This one protects every sound and ends a clip 20 ms after the last word. |
| **style** | Codes every line into four layouts (IN BIG split screen, IN SMALL, OUT full graphic, FULL speaker) and places the speaker and graphics by exact pixels. Slow zooms. Nothing in the phone's crop zone. | Left alone, AI keeps you in one box the whole video and puts text where the phone crops it off. This keeps your layout the same every time. |
| **captions** | Makes the captions from your word timings: two or three words a screen, never more than three, placed where they read best in each layout (above your head, in the split-screen seam, low on full-frame shots) and rendered on their own layer. Plain digital font by default, swap it in one line. | Left alone, AI crams long captions all over the screen and on top of your face. This puts them in the right spot every time. |
| **sound-effects** | Puts a sound on every movement at its exact frame, picked from a 45-sound bank for what actually fits. One riser after the hook. Audits the final file and replaces anything wrong. | AI picks the same sound for everything. This picks by fit, gives each sound one job and never repeats one on neighbouring moments. |
| **motion-graphics** | Builds Remotion graphics from real logos and real screenshots, with a camera that moves through one continuous scene. Ships with three helper skills: `cinematic-camera`, `terminal-inserts` and `article-highlights`. | So it doesn't look like generic AI animation. No neon, no glowing gradients, no fake dashboards. |

## Set it up

1. Install the [Claude desktop app](https://claude.ai/download) and open Claude Code.
2. Make a folder called **AI Video Editor** and open Claude Code in it.
3. Paste in the prompt from [SETUP-PROMPT.md](SETUP-PROMPT.md). It installs everything Claude needs: ffmpeg, Python packages, a Remotion project, the official Remotion skill, the caption font and the caption layer.

## Use it

Drop your raw footage into `footage/` and say:

> Edit this.

Claude cuts it first, then shows you a table of which layout each line gets. Approve it (or change any row), and it builds the graphics, places everything, captions it and adds the sound. If something's off, tell it what to change in one message.

Works best with talking-head footage shot vertically or in 4K, looking at camera, with a lav or wireless mic.

## What's in here

```
.claude/skills/
  cut/              the cut skill + scripts (transcribe, gaps, dropouts, picture jumps)
  style/            the layout skill + layout.json (every pixel) + checks (coverage, side crop)
  captions/         the captions skill + caption maker + Captions.tsx (the Remotion caption layer) + caption check
  sound-effects/    the sound skill + the 45-sound bank + mix builder and audit
  motion-graphics/  the graphics gate + logos and approved reference renders
  cinematic-camera/ terminal-inserts/ article-highlights/   helpers the graphics skill uses
CLAUDE.md           the editing order Claude follows
SETUP-PROMPT.md     the prompt you paste once
```

## Credits

Motion graphics skills adapted from [remotion-motion-graphics-skill](https://github.com/Liamrjohnston/remotion-motion-graphics-skill). Caption font: [Departure Mono](https://departuremono.com) (SIL Open Font License). Some sounds: [Kenney](https://kenney.nl) and Sonic Pi samples, CC0.

## Licence

MIT. See [LICENSE](LICENSE).
