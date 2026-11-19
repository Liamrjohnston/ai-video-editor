---
name: captions
description: "Make the captions for a talking-head Reel: two or three words a screen and never more than three visible, built from the cut's word timings, placed where they read best in each layout (just above the head, in the split-screen seam, or low in full-frame shots) and rendered on their own layer so zooms never touch them. Plain digital font by default; swap it in one line. Use after the cut."
---

# Captions

Left alone, AI crams long captions across the screen, drops them on top of the speaker's face or a graphic, and lets them zoom with the camera. This skill fixes the placement and the pacing. The font is a plain default you can change; where the captions go and how many words show is what matters.

You need: `words.json` (word timings from `cut/scripts/transcribe.py`, re-timed to the final cut) and `modes.json` (which layout mode starts at which frame, from the style skill's coverage map). Without a coverage map, every caption uses the IN SMALL position.

## Font

- Default: **Departure Mono**, a free digital-style font (SIL Open Font License), in white, one line, no background box. It's clean and readable on a phone.
- Want a different font? Put the file in `remotion/public/fonts/` and change `FONT_FILE` and `FONT_NAME` at the top of `Captions.tsx`. Size is `FONT_PX` (default 40). Keep one font and one size for the whole video.

## Where captions go

These positions come from measuring real phone screens with the Instagram interface on top, so captions never land on the face, a graphic or the app's buttons.

| Layout | Caption centre (1080x1920) | Why |
| --- | --- | --- |
| IN SMALL | (540, 1262) | Just above the speaker's head and below the graphic area, with clear space on both sides. |
| IN BIG | (540, 962) | In the faded seam between the graphic and the speaker, where nothing else sits. |
| OUT, FULL, call to action | (540, 1489) | Low in the frame, clear of the main content and above the app's caption and buttons. |

- **Same size in every layout.** Only the position moves.
- **Captions never follow a camera zoom.** They sit on their own top layer so their size and position never drift.
- **Check the whole move, not one still.** Captions stay above the highest point the hair reaches and below the lowest important graphic for every frame they're up. If a take puts the head higher, move the speaker, not the caption.
- **Big text steps in for captions.** In FULL, when the style skill shows the line as big text above the head, the regular caption steps aside.

## How many words

- **Two to three words a screen, never more than three visible at once in the whole frame.** That's a total for the screen, so an outgoing and incoming caption can't overlap into four.
- Two long words together get a screen of their own. One word alone is fine for emphasis, a name or a natural remainder.
- Break where the speaker breaks: sentence ends, commas, real pauses.
- Every spoken word appears exactly once, in order. Never drop, duplicate or paraphrase. Never shrink the font to fit a phrase; split it instead.

## Make them

```bash
.venv/bin/python .claude/skills/captions/scripts/make_captions.py words.json --out captions.json --modes modes.json --srt captions.srt
```

It splits each phrase into the fewest, most even screens of two or three words, gives a crowded three-word screen an extra screen, keeps every word exactly once and sets each caption's position from the layout it starts in. The `.srt` is for anyone finishing in CapCut or another editor.

## Render them

Copy `references/Captions.tsx` into the Remotion project and put `<Captions captions={captions} />` as the top layer of the edit, outside every zoomed or scaled container.

## Check them

```bash
.venv/bin/python .claude/skills/captions/scripts/check_captions.py captions.json --words words.json
```

Then look at encoded frames at phone size: the first caption, every layout, every transition, the longest phrase and every place a caption could touch hair, a hand or a graphic.

Re-make captions after every cut change, then check again.
