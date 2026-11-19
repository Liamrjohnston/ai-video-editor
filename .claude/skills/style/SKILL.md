---
name: style
description: "Keep a talking-head Reel's layout the same every time. Codes every line into four modes (IN BIG, IN SMALL, OUT, FULL), places the speaker and graphics by exact pixels and adds the slow zooms. Captions are the separate captions skill. Use after the cut and before or alongside motion graphics."
---

# Style: layout

This skill is the house look. It decides where the speaker sits, where graphics go and when the layout switches. It exists because an AI left to itself keeps the speaker in one box for the whole video and puts text where the phone crops it off. Every number lives in `references/layout.json`. Read it before placing anything.

All work is on a native **1080x1920** canvas.

## The four modes

| Mode | What's on screen | When |
| --- | --- | --- |
| **IN BIG** | Half split screen. Graphic on the top half, the speaker full width on the bottom half, the seam faded so no line shows. | Every video opens here. Use when the speaker matters as much as the proof: an opinion, a personal stake, a picture being painted. Proof that fits a wide box (one passage, a chart, two clips side by side). |
| **IN SMALL** | Graphic gets the big upper stage. The speaker sits small in a rounded panel on the bottom edge, head breaking above the panel. | When the graphic needs height: tall pages, long lists, grids, phone screens. |
| **OUT** | Graphic fills the whole frame. Speaker not visible. | When the scene needs everything: a crowded UI, a wall of results, fast motion. |
| **FULL** | Speaker full screen, no motion graphic. The line they're saying appears as big text above their head. | Only on a genuine transition, a bridge that needs nothing shown. |
| **NONE** | No asset of its own; the neighbouring graphic holds or starts early. | A line that's covered by the graphic next to it. |

Viewers should see the speaker fully, half, small and gone, so they never know where the speaker will be next, while it still feels like a natural talking-head video and never like an AI avatar.

## Step 1: the coverage map (before anything is built)

1. Take the script the speaker actually filmed. If you have the transcript from the cut, use the spoken words, not the written script.
2. Number rows by sentence (1, 2, 3). Split a sentence into a/b where its job changes, for example a setup and then a payoff (3a, 3b).
3. Estimate time per row at about 3.5 spoken words a second until the real cut exists, then use the real timings.
4. **Find FULL moments word by word.** FULL covers only the neutral bridge that needs nothing shown, and it ends before the first word that needs a visual, even mid-sentence. Example: "Let's use this tool / for a client's website launch." Only "Let's use this tool" is FULL; the visual starts on "for". "And here's the result" is not automatically FULL: the result can already be playing. One or two natural FULL moments per video, or none. Never pad one, never more than 4 seconds, never on the hook or the row straight after it. A call to action is not automatically FULL.
5. Code every other row IN BIG, IN SMALL or OUT by what the line needs, then apply the switching rules:
   - Row 1 (the hook) is always **IN BIG**. A natural opening run is IN BIG, then IN SMALL, then OUT, then FULL if a line suits it.
   - The same mode can run **two rows in a row, never three**.
   - **Never two OUT rows in a row.**
   - **OUT 3 to 4 times per video.** The speaker is in shot for everything else.
   - Not every line needs its own graphic. A NONE row follows its neighbour.
   - IN BIG into IN SMALL is a shrink and reads best when the same graphic world carries on, so plan those rows together.
6. Show the user the table and stop:

   | # | Line | Mode |
   | --- | --- | --- |
   | 1 | Hook: "..." | IN BIG |
   | 2 | "..." | IN SMALL |
   | 3a | "..." | OUT |
   | 3b | "..." | **FULL** |

   Under it, one line each: estimated length, rows and seconds per mode, which rows become graphics, any wording that differs from the script.
7. Apply their corrections and show it again if anything moved. Save the approved map as `coverage.json`, for example `[{"row": 1, "line": "...", "mode": "IN_BIG", "startSec": 0, "endSec": 2.5}]` (modes: IN_BIG, IN_SMALL, OUT, FULL, NONE), and check it:

   ```bash
   .venv/bin/python .claude/skills/style/scripts/check_coverage.py coverage.json
   ```

   Build nothing until the user approves the map.

## Step 2: eye line overrides the map

Classify every used segment, and every visible frame including transitions, by where the speaker is looking.

- **Looking down** (at notes, a laptop, a phone): OUT, whatever the map says.
- **Looking at camera:** IN BIG or IN SMALL as the map assigns.
- **FULL needs them looking up** at camera.
- **The hook must be IN BIG and looking up.** If it isn't, look for another take of that line first.
- **Hard cut, not slide, when the eyes drop.** Cut to OUT on or before the first frame the head starts to drop. Only slide or shrink when they look at camera for the whole move, otherwise the move shows them looking down.

## Step 3: place the speaker

**IN SMALL** (exact values in `layout.json`):
- Panel x71 to 1009 (938 wide), top y1410, corner radius 40, running about 5 px off the bottom so it sits on the edge. The 71 px side margins clear the Reels-tab side crop; a 46 px margin gets its corners clipped.
- Head top at **y1310**, about 100 px above the panel, with a synchronized head cutout overlapping the panel top by 16 px. Use the smallest uniform scale that fills the panel width.
- Measure the head top as the **median across every IN SMALL frame** of the take, never from one still. One still put a real take 17 px too low.
- Never show the speaker with their whole head inside the panel. Put them higher, not lower.
- If a chin or face moves into the app's bottom interface on a take, a small speaker-only lift is fine. Don't change the panel, caption or graphic area for it.

**IN BIG:**
- Speaker panel full width from y960 to the bottom, rounded top corners (radius 84). Head top about y1060.
- No head cutout in IN BIG: a solid cutout leaves a hard, flickering edge around hair.
- The graphic is solid down to y770 and gone by y940 on a smoothstep curve; the footage rises out of the same background over its top 250 px on the same curve. A linear fade leaves a visible line. No border, no divider.

**IN BIG to IN SMALL** is a 30-frame (about 1 s) inOut cubic shrink where everything moves together: panel, camera, feather to a hard edge, head cutout fading in at eased progress 0.2 to 0.45, graphic re-centring to y686, caption dropping to y1262. The head breaks above the panel on the way down. Reverse it to grow back.

**Background:** one seamless full-frame surface behind everything, matching the surface the motion-graphics skill uses for the video. No divider, border, safe-zone mask or separate card behind the graphics.

## Step 4: camera moves

- **Slow zoom on every IN BIG.** The footage starts at 100% on the first frame of each IN BIG stretch and pushes in at a steady 1.3% a second, centred on the face (about 540,1210), capped at 108%. A 4.5 second stretch ends near 106%. It resets to 100% at the next IN BIG. Only the footage moves; panel, fade, caption and graphic stay still. If the stretch ends in a shrink, ease the zoom back to 100% inside the shrink. **Never on IN SMALL.** It's barely noticeable, but it's movement, and movement keeps people watching a flat lower screen.
- **FULL gets big text and a small zoom.** The footage zooms 3% a second from 100%, capped at 106%. The line being said is typed on the spoken word as big terminal-style text between the top of the frame and the hair (y150 to 600): a small lead-in around 44 px, the key words around 100 px, fitted inside x120 to 960. Add a soft dim of the room above the head so white type reads on a bright wall, never a bar or box. Regular captions step aside while it's up.
- **Optional opening pullback:** the speaker's panel eases from 110% to 100% over about 1 second at the start. Captions and graphics stay fixed.
- **Closing pushes** stay subtle and continuous across cuts in the call to action.

## Step 5: captions

Captions have their own skill: `captions`. It uses the mode positions from `references/layout.json`, so code the modes first.

## Step 6: place graphics in the modes

- **Readable area is x120 to 960** in every mode. Instagram's full-screen view crops about 97 to 108 px off each side, so a percentage or a word near the edge gets cut off.
- IN BIG graphics keep important content inside x120 to 960, y250 to 760 (above y250 is the phone's status area and top controls). IN SMALL graphics stay inside x120 to 960, y200 to 1172, which leaves 54 px of clear space above the caption. OUT keeps readable content inside x120 to 960.
- Author graphics at their final size inside the area. Never shrink a finished render to fit; reflow or simplify the foreground instead. Native assets assemble at scale 1.0.
- Switch modes at a real explanation, reveal or cut, never on a timer.
- **Re-time finished graphics to the cut by pinning** each visible action to the word it shows (take the action frames from the graphic's own code). Run the graphic's clock linearly between pins, cap motion at 1.3x, and absorb fast speech by compressing static holds, never by speeding up the motion. Start graphics that open blank a few frames in, so a straight cut never lands on an empty frame. Trim an ending where something new would flash on in the last 1 to 3 frames before a cut.
- In Remotion: wrap each asset in `<Freeze frame={designFrame}>`, keep real footage at 1x on its own edit clock outside any `<Sequence>`, and make each composition at least as long as its design.

## Step 7: the ending

Read the script's close before calling it face-only. Find the actual comment keyword, the resources promised and any share line. Then, when the script calls for it:

1. The keyword appears **large above the head**, then slides up on the handoff.
2. The real promised resources **rise from behind the head**. Use the real deliverables, never generic invented cards.
3. They clear before a share popup, which only appears if the speaker actually says a share line. Hold it on that line and remove it right after.

Each of those movements gets a sound in the sound-effects skill. Never invent a spoken line or a resource.

## Step 8: check

```bash
.venv/bin/python .claude/skills/style/scripts/check_side_crop.py final.mp4
```

It must pass (exit 0). Then watch the encoded file at phone size. A passing script is not the same as looking at it.

## Rules

- The coverage map is approved before anything is built.
- Hook on IN BIG, looking up. Two in a row, never three. Never two OUT in a row. OUT 3 to 4 times. FULL only on a real transition, 4 seconds max.
- Captions follow the captions skill, at the positions in `layout.json`.
- Every readable thing inside x120 to 960.
- Never overwrite an accepted version. Every change is a new numbered version.
