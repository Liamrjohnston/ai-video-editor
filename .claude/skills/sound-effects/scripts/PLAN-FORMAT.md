# plan.json format

The plan is the one file every sound tool reads. It says what moves in the video, when, how many sounds it needs and
which bank sounds suit it. You write it from the graphics code (frames come from the code, never from eyeballing).
`fit.py` fills in the chosen sounds, `build_mix.py` makes the mix, `audit_mix.py` checks the encoded video against it.

Frames are frame numbers of the final video (frame 0 is the first frame). Times are seconds. A sound is always a number
from the bank (`bank.py list`).

## Top level

| field | needed | meaning |
|---|---|---|
| `fps` | yes | frames per second of the video, for example 30 |
| `totalFrames` | no | length of the video in frames. If missing, it is taken from the voice track |
| `cues` | yes | the list of movement cues (below) |
| `riserPolicy` | if a riser is used | `{"onlyCue": "<cue id>", "why": "<one sentence>"}`. The only cue allowed a riser sound |
| `roleLoudness` | no | perceived-loudness targets in LUFS per role, overriding the defaults: `swoosh -24.4, riser -28.4, pop -29.3, press -29.4, tick -34, typing -38` |
| `roleWindowSec` | no | loudness window, default 0.1 |
| `reusePolicy` | written by fit.py | `{"swooshMinGapSec", "otherMinGapSec", "why"}`. How far apart a repeated sound must be. Default 20 s; anything under 20 needs a `why` |
| `repeats` | written by fit.py | `[{"sound": 14, "cues": ["A", "B"], "why": "..."}]`. Every sound used on more than one cue must be listed here |
| `music` | no | `{"file", "startSec", "underVoiceLU", "loop": {"startSec", "endSec", "crossfadeSec"}, "fadeOutSec", "excludeFromSec"}`. Start offset into the file, held `underVoiceLU` (default 12) LU under the voice, optional loop between two points of the file, optional guard that fails if the music clock reaches `excludeFromSec` |
| `graphicsRegion` | no | `[top, bottom]` as fractions of the picture height (default `[0, 1]`) that audit_mix watches for picture changes |
| `footageSpans` | no | `[{"from": frame, "to": frame, "why": "..."}]`. Footage playing inside a graphic; motion_gaps reports it but does not fail it |

## A cue

| field | needed | meaning |
|---|---|---|
| `id` | yes | short unique name |
| `what` | yes | what moves, in plain words |
| `frame` | yes | the frame the movement starts (from the code) |
| `hits` | if count above 1 | the frame of every sound. Defaults to `[frame]` for one hit |
| `count` | no | exact number of hits. Must equal the length of `hits` ("4 blips and only 4 blips") |
| `motionEnd` | yes | last frame of the movement. A sound may not ring more than 3 frames past it |
| `align` | no | `"onset"` (default): the first audible moment lands on the hit frame. `"peak"`: the loudest moment lands on it (swooshes on zooms and camera moves, and the riser) |
| `motionStart` | no | for `peak` cues, the first frame of the move (default `frame`). Nothing may be audible more than 1.5 frames before it |
| `cutFrame` | no | frame of a straight cut out of the graphic. A sound may not ring more than 3 frames past it |
| `fit` | for fit.py | `{"list": [...], "why": "..."}`. Bank numbers, best first. A nested list is one tier of equally good sounds: `[84, [104, 108]]` means 84 first, then 104 or 108 equally |
| `sound` | after fit | the chosen bank number. A cue with `sound` and no `fit` is pinned and kept as is |
| `soundFile` | no | a file path instead of a bank number. It is hashed and refused unless it matches a bank entry |
| `gainTrimDb` | no | a manual level trim for this cue, on top of the automatic role level |
| `multiPulse` | no | a reason, for a single-hit cue whose sound is a deliberate run of many tiny clicks (more than 2 pulses) |
| `choice` | written by fit.py | 1 for the first tier, 2 for the second |

## Rules the tools enforce

- Every sound is a bank sound (sha256 re-checked) and not in `bank/banned.json`.
- Hits equal count. Hits closer together than 1/12 s (a fast cascade) are refused: use one sound for the whole cascade.
- Counted cues take one-pulse sounds. A sound with two blips far apart, or a run of many, cannot go on a counted list.
- Fit first, then spacing. The same sound never sits on neighbouring cues; a repeat is declared and kept at least the
  policy gap apart. Typing sounds may repeat.
- One riser at most, only on `riserPolicy.onlyCue`, single hit, `align: "peak"`. A riser sound anywhere else fails.
- Nothing audible more than 1.5 frames before its movement. Tails end by `motionEnd` plus 3 frames.
- Levels match each role's target; any cue within 6 dB of the voice is trimmed. No limiter, compressor or ducking.

## Worked example

```json
{
  "fps": 30,
  "totalFrames": 180,
  "riserPolicy": {"onlyCue": "RISER", "why": "One build from the opening into the main point, on the cut."},
  "cues": [
    {"id": "BLIPS", "what": "Four items appear one after another", "frame": 30,
     "hits": [30, 36, 42, 48], "count": 4, "motionEnd": 52,
     "fit": {"list": [84, [104, 108]], "why": "A tiny bright blip for each item that appears."}},
    {"id": "RISER", "what": "Cut from the opening into the main point", "frame": 60,
     "hits": [60], "count": 1, "align": "peak", "motionEnd": 70,
     "fit": {"list": [44], "why": "The one build into the cut."}},
    {"id": "ZOOM", "what": "Camera pushes in on the card", "frame": 90, "motionStart": 90,
     "hits": [100], "count": 1, "align": "peak", "motionEnd": 118,
     "fit": {"list": [24, [23, 26]], "why": "Soft air sized to a medium push, peaking on its fastest frame."}}
  ]
}
```

The three cues above give 4 + 1 + 1 hits. The riser's loudest moment lands on frame 60 and it starts earlier (a riser
builds before its hit, so the early-audio rule does not apply to it). The zoom's swoosh peaks on frame 100, the zoom's
fastest frame, and may not start more than 1.5 frames before frame 90.

## Order of work

1. `fit.py plan.json --out plan.fit.json` chooses the sounds and writes `repeats` and `reusePolicy`.
2. `build_mix.py plan.fit.json --voice voice.wav --out mix_dir` writes `mix.wav`, `sfx.wav` and `sound-ledger.json`.
   If any rule fails it prints every problem and writes no `mix.wav`.
3. `mux.py picture.mp4 mix_dir/mix.wav final.mp4` joins picture and mix (picture stream copied).
4. `audit_mix.py final.mp4 --plan plan.fit.json --ledger mix_dir/sound-ledger.json --out audit.json` checks the result.
5. `motion_gaps.py graphics.mp4 --plan plan.fit.json --out gaps.json` finds graphic motion with no sound.
6. `levels.py` and `cue_sheet.py` report levels and write a readable sheet.
