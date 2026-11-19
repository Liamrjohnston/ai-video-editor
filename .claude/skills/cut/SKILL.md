---
name: cut
description: "Cut raw talking-head footage into a tight spoken edit. Finds the best complete take of every line, removes every bit of dead air down to the frame, never clips the end of a word or chops a breath in half, and checks every join for picture jumps, mic dropouts and voice level. Use first, on the raw recording."
---

# Cut: the tight spoken edit

The cut is the foundation. Graphics, captions and sound are all timed to it, so it has to be right before anything else starts. The standard: **the first version is cut super tight, with not a single bit of dead space anywhere, and nothing overlapping.** Tight never means clipped. A word that loses its last consonant, or a breath cut in half, sounds worse than a pause.

## What you need

- The camera original video. Never the low-res proxy file some cameras write next to it (a DJI `.LRF`, for example): cut from the full-quality MP4.
- The script, if there is one.
- ffmpeg, and a local transcriber (faster-whisper). Transcribe locally; never upload someone's footage to an outside service.

## Step 1: inventory

Probe the source: resolution, exact frame rate (29.97 is `30000/1001`, not 30), duration, audio channels. Record it. Every frame number in this skill is a native frame of the source. Never adopt another video's frame rate.

## Step 2: transcribe with word timings

```bash
.venv/bin/python .claude/skills/cut/scripts/transcribe.py raw.mp4 --out words.json
```

Speech-to-text finds words. It cannot judge delivery, hear a mumble or certify a clean consonant.

## Step 3: scan for mic dropouts before cutting

Wireless mics sometimes lose 20 to 50 ms and fill it with a smooth fake decay. It sounds like a glitch on a word, and people blame the edit.

```bash
.venv/bin/python .claude/skills/cut/scripts/find_dropouts.py raw.mp4 --json dropouts.json
```

Run it on the source audio, never on a finished mix where music hides it. Repair each real dropout, then cut from the repaired audio:

```bash
.venv/bin/python .claude/skills/cut/scripts/repair_dropout.py raw.mp4 --start 32.722 --end 32.762 --out audio_repaired.wav --json repair.json
```

The repair deletes the concealment, crossfades the two real halves, and makes up the time with room tone from the nearest pause, so lip sync holds. No synthesis, filtering or gain. When someone says "there's a glitch", check sound and picture separately.

## Step 4: pick the takes

- **Listen for spoken cues.** Speakers often say "use that one", "that's the one" or "use this one" after a good take. The cue marks the completed take **just before it**. With no cue, the last clean complete take before they moved on. A later spoken override wins.
- **Never pick the last take by default.** It's often the tired one.
- **Reject** mumbles, false starts, unfinished thoughts, interrupted words, quiet rehearsals and misreads. Never rescue a quiet take with gain.
- **For any suspect line, search the whole recording** for every complete take of it, not just the nearest one. Compare them in a short table: take, source time, cue, verdict, reason.
- **When it isn't clear which take sounds best, ask.** Give the user every complete take of that line to play, with any cued take preselected, and cut from their picks. Don't guess on delivery.
- If no clean complete take of a line exists, say so plainly. Never invent a replacement or bridge from a word fragment.
- Compare the script to the actual spoken words line by line. Graphics and captions follow what was said, not what was written.
- **Multiple hooks:** if several opening hooks were recorded, cut the body once and each hook separately, then check every hook-to-body join on its own.

## Step 5: cut tight

```bash
.venv/bin/python .claude/skills/cut/scripts/find_gaps.py audio_repaired.wav --words words.json --json gaps.json
```

This proposes candidates; it never cuts. Then go boundary by boundary:

- Remove all discretionary dead space: between takes, between sentences, between words, tail holds. Join straight to the next meaningful speech.
- **Keep only the frames a sound actually needs:** weak fricatives (s, f, th), aspirates (h), consonant closures and releases (t, k, p), and the full decay of a word ending. For every KEEP, name the protected sound. "Natural pacing" is not a reason.
- **Breath tails.** Where the level falls toward room tone and then rises again with no word, that rise is a breath. End the piece **20 ms after the word's last sound**. Cutting into the breath leaves a strange half-noise. A decaying word ending stays.
- Keep at least 2 frames before a word that starts after a removed pause.
- Never speed up the voice, never overlap two pieces of speech, never crossfade two voices on top of each other. Never remove real speech to hit a duration.
- A silence detector proposes candidates; it never certifies anything. Tiny gaps below a detector's minimum still get reviewed.

Write a frame-exact manifest (`cut.json`): for each piece, the line it belongs to, source in and out frames, output start frame, and the reason for each boundary. Everything downstream (captions, graphics, sound) is re-mapped from it after every change.

## Step 6: picture jumps at joins

Cutting a short pause while the hands or head are moving looks like dropped frames. After the tight pass, render the cut and measure every mid-sentence join:

```bash
.venv/bin/python .claude/skills/cut/scripts/join_jumps.py cut.mp4 --cut cut.json --modes modes.json --json jumps.json
```

The jump is the frame difference across the join divided by the normal motion around it. **At 3x or more**, put back the fewest real pause frames that bring it to **2x or less**, choosing which frames to drop so the two sides match. No dissolves. Cuts between takes at sentence breaks are normal jump cuts. Joins hidden under a full-screen graphic don't show. On a line where the hands move fast, cut no frames inside it at all.

## Step 7: even voice

Level every take and pickup per sentence before showing anything, so it sounds like one recording. Check tone on a phone-like curve, and pitch: **takes 1.5 semitones apart still sound off** at a join. A re-record beats a pitch shift. Two halves of one hook recorded seconds apart can still differ; pick the pair that matches best, and if the picture jumps at that join, cover it with a punch-in.

## Step 8: audit before anyone sees it

Transcribe the exported cut independently and compare the words in order to the intended lines. Check for duplicated starts ("now you can, now you can review") with short overlapping windows around every join, because whole-file speech-to-text smooths repetitions away. If someone reports a repeat, it's real until proven otherwise.

Save a receipt with every version:

- **Coverage:** how many pieces, heads, tails, joins and gaps were reviewed. Expected and reviewed counts must match.
- **Take ledger:** intended words, every candidate take for suspect lines, the choice and why.
- **Cut ledger:** each boundary's frames, frames removed or kept and the specific sound protected.
- **Residual gaps:** rerun on the encoded cut; list anything left and why it stays.
- **Listening:** an automated check is not listening. Mark listening **PENDING** until a person has heard it at normal speed. Never claim it sounds clean because the numbers passed.

## When feedback comes back

- A rejected mumble or a "this cut is loose" note means **re-audit the whole video**, not just that timestamp.
- Every correction is a new version. Never overwrite an accepted cut.

## Rules

- Tight from version one. No dead space, nothing overlapping, no clipped sounds.
- Cue-led takes. Never the last take by default. Ask when delivery is unclear.
- Breath tails end 20 ms after the last word.
- Joins at 3x motion or more get frames back to 2x or less. No dissolves.
- Scan and repair mic dropouts on the source before cutting.
- Never speed up or synthesize the voice. Never upload footage.
