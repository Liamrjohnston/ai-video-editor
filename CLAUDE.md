# AI Video Editor

This folder is a video editor run by Claude Code. The user drops raw talking-head footage in `footage/` and says "edit this". You take it from raw recording to a finished 9:16 Reel with four skills:

| Skill | Job |
| --- | --- |
| `cut` | The tight spoken edit: best takes, zero dead air, no clipped words or half breaths |
| `style` | Layout and captions: the four modes (IN BIG, IN SMALL, OUT, FULL), exact placement, slow zooms, three-word captions |
| `sound-effects` | A sound on every movement from the 45-sound bank, one riser, audited on the final file |
| `motion-graphics` | Remotion graphics built from real logos and real screenshots (with `cinematic-camera`, `terminal-inserts` and `article-highlights`) |

## The order

1. **Cut** (`cut`). Transcribe, scan for mic dropouts, pick takes, cut tight, check joins and voice level. Show the cut first; if a take choice is unclear, show every take of that line and let the user pick.
2. **Coverage map** (`style`, step 1). Code every line IN BIG, IN SMALL, OUT, FULL or NONE. Show the table and wait for approval. Nothing gets built before this.
3. **Graphics** (`motion-graphics`). Build the approved rows, hook first, real assets only, in the mode's exact area.
4. **Place and caption** (`style`). Speaker framing per mode, eye-line rule, zooms, graphics pinned to the spoken words, the ending, then captions: `make_captions.py` from the cut's word timings, rendered with `Captions.tsx`, checked with `check_captions.py`.
5. **Sound** (`sound-effects`). Every movement, fit first, one riser, then the audit on the encoded file.
6. **Music** (optional, `sound-effects`). Only the user's own licensed tracks. Two or three versions for them to pick from.
7. **Final check.** `check_side_crop.py` passes, the sound audit passes, every caption check passes, then watch the encoded file at phone size.

If the user asks for the whole thing in one go, run every stage without stopping and log each decision and its reason in `edits/<video>/log.md`, then present everything in one review.

## Working rules

- **Work in `edits/<video name>/`.** Keep the raw footage untouched. Number every version (v1, v2, ...) and never overwrite one the user accepted.
- **When the user says something's off, change only that,** in one new version, and say exactly what changed. A note about a mumble or a loose cut means re-checking the whole video, not just that second.
- **Footage stays on this computer.** Transcribe locally. Never upload the user's video anywhere without being asked.
- **Automated checks are not listening or watching.** Say "checked by measurement" or "looked at the frames", and mark listening PENDING until the user has heard it.
- Heavy renders take a while. Tell the user what's rendering and roughly how long, and check the output exists and plays before saying it's done.
