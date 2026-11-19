---
name: sound-effects
description: "Put a sound effect on every movement in a Reel, at the exact frame it moves, chosen from a curated 45-sound bank for what actually fits. One riser after the hook, exact hit counts, no repeats on neighbouring moments, voice always on top. Then audits the encoded video and replaces anything that fails. Use after the picture, graphics and captions are locked."
---

# Sound effects

Sound is what makes motion feel premium. Two failures make it feel cheap: **movement with no sound** ("things are moving and there's no sound for it") and **the same sound spammed everywhere** (an edit where almost every effect was a laser zap). This skill fixes both. Every movement gets a sound, each sound is picked for what fits, and the whole mix is audited on the final file.

## The bank

`bank/BANK.md` is the bank: 45 numbered sounds, each with what it sounds like and the one job it's best at. `bank/bank.json` has the same data plus a sha256 for every file.

- **Pull sounds from the bank and nowhere else.** The builder re-hashes every file and refuses anything that isn't an entry in `bank.json`. This stops a random download sneaking in.
- **To add a sound,** listen to it in context, add it to `bank.json` with its sha256 and a job, and only then use it. To ban one, move it to `bank/banned.json` and it will be refused from then on.
- **Never use:** dings (most chimes sound cheap; #94 is the only one, and it's rare), laser zaps, bicycle-wheel or ratchet sounds, or typewriter typing.

Check the bank is intact:

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/bank.py verify
```

## Step 1: freeze the picture, then list every movement

Sound comes after picture, captions and graphics are locked. Then list **every** movement, from the graphics' code and the final retimed picture, not from memory:

- typing and its pauses, clicks, cursor moves
- camera zooms in and out, pushes, pull-backs, pans
- things travelling, sliding, flying in, landing
- grouped reveals and pops, counted items, numbers climbing
- connections drawing, things orbiting, exits
- mode changes in the layout (a shrink, a hard cut to full screen)
- the ending: keyword appearing above the head, resources rising, share popup

Each movement is a cue with its exact frame. Take frames from the code and map them through the cut's retiming. Never infer timing from file names or unretimed timestamps.

Then scan for anything you missed:

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/motion_gaps.py graphics.mp4 --plan plan.json --out gaps.json
```

It lists every run of visible motion with no cue near it. Give each strong one a sound, or a specific reason. **"Sparse" or "premium" is not a reason to leave real movement silent.**

## Step 2: write the fit list, then solve

For each cue, write the sounds that actually fit what moves, best first, with one line on why. The bank's "Best job" column is the starting point. Examples:

| What moves | Fits |
| --- | --- |
| A window, menu or card opens | #16 UI pop, else #17 Button |
| A cursor clicks something | #14 Mouse click, else #12 Crispy click |
| Something pops in with an overshoot | #15 Pop, else #136 Drop bloop or #16 |
| A marker highlights a word | #21 Select |
| A line of text appears in a terminal or chat | #108 or #105 tiny ticks |
| A caption or label appears on a graphic | #102, #104 or #128 |
| A camera push or zoom in | #24 Short swoosh, peaked on the zoom's fastest frame |
| A big pull-back | #23 Soft swell swoosh |
| A quick swipe or glide | #26 Air puff |
| Visible typing | #35 Typing key, one per keystroke |
| Something switches off | #110 Switch press |

Rules for the choice:

- **Fit first, then spacing.** Each sound keeps one job across the video. A small palette where each sound means one thing sounds designed; a big random palette sounds like noise.
- **Never the same sound on two neighbouring cues.**
- **Repeats are fine when they fit,** spaced as far apart as fit allows, and every repeat is listed.
- **One riser per video**, and only one: on the cut from the hook into the main point, peaking on that cut. Riser sounds (#41, #39, #44, #40) go nowhere else. A zoom never gets a riser; it gets a swoosh.
- **Exact counts.** If something blinks four times, it gets four hits. Not three, not five. A cascade faster than about 12 a second gets one sound for the group.
- **Typing only while text visibly types**, quiet, under the voice and the music. Retained taps at least 6 frames apart; a dense run of key hits turns into a rattle.
- **Nothing audible more than 1.5 frames before its movement,** and the tail ends before the movement stops. Swooshes peak on the fastest frame of the move.

Write the plan (format in `scripts/PLAN-FORMAT.md`), then solve it:

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/fit.py plan.json --out plan.solved.json
```

The solver keeps every cue on its first or second choice and pushes repeats as far apart as it can.

## Step 3: levels

- **The voice leads.** Sound effects are audible but restrained. No limiter, compressor or automatic ducking on the mix.
- Match each kind of sound (clicks, swooshes, pops, typing) to a consistent perceived loudness, then trim any cue that comes within 6 dB of the voice around it.
- Too quiet is a real failure too: effects that sit about 18 dB under the voice peak read as missing.

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/levels.py mixdir/sound-ledger.json --voice voice.wav --out levels.json
```

## Step 4: build

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/build_mix.py plan.solved.json --voice voice.wav --out mixdir/
```

For a music bed, add a `music` block to the plan (file, start, how far under the voice; see `scripts/PLAN-FORMAT.md`). The builder also keeps the voice clear of every effect automatically. The builder refuses to write a mix while any problem is listed: a file not in the bank, a riser in the wrong place, a wrong hit count, a repeat on neighbouring cues, audio before its movement. Fix the cause and rebuild.

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/mux.py picture.mp4 mixdir/mix.wav final.mp4
```

## Step 5: audit the encoded file, replace, re-check

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/audit_mix.py final.mp4 --plan plan.solved.json --ledger mixdir/sound-ledger.json --out audit.json
```

The audit decodes the actual final video and checks every hit is there at its sample position, counts are exact, there are no stray sounds, every file is still a bank file, the riser rule holds and no neighbouring cues share a sound. Fix every failure at its cause, rebuild and run it again until it's clean. Nobody sees the video before the audit passes.

## Step 6: report

Make the cue sheet:

```bash
.venv/bin/python .claude/skills/sound-effects/scripts/cue_sheet.py mixdir/sound-ledger.json cues.csv
```

Tell the user: how many sounds, why each fits, second choices, every repeat with its times, what the audit caught and fixed. **An audit is not listening.** Mark listening PENDING until a person has heard it at normal speed on a phone.

## Music bed

Bring your own music, and only music you have the rights to use. Some guidance that held up across many edits:

- Sit the bed about **14 dB under the voice** (`"underVoiceLU": 14` in the plan). If the viewer can't hear it, bring it to 9 to 12 dB under. Measure the bed on its own, then actually listen under the speech.
- Start the track where it's already moving, not at a slow intro.
- If the video runs past the track's good section, loop it back before the outro with a short crossfade on the beat, rather than letting a different-sounding ending play.
- Give the user two or three versions with different tracks, everything else identical, and let them pick.

## Rules

- Bank sounds only, matched by sha256.
- A sound on every movement, at its code frame, with exact counts.
- Fit first. Each sound one job. Never the same sound on neighbouring cues. Every repeat listed.
- One riser, after the hook into the main point. Zooms get swooshes.
- Typing only on visible typing, quiet.
- Voice on top. No ducking, no limiter.
- Audit the encoded file, replace failures, re-check. Listening stays PENDING until someone listens.
