#!/usr/bin/env python3
"""Join the finished picture and the mix into the final mp4 without touching the picture.

The video stream is copied (no re-encode, so the picture is bit-identical), the audio is encoded as AAC, 48 kHz,
stereo, 320 kbps. Afterwards it proves the result: the picture stream is identical to the input picture, the frame
count is unchanged, the mix has no clipping, and the encoded audio still matches mix.wav. Exit 1 if any check fails.

  mux.py picture.mp4 mix_dir/mix.wav final.mp4 [--encoder aac_at]
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np

import sfxlib as S


def probe(path):
    r = subprocess.run([S.ffmpeg_bin("ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def packet_md5(path):
    r = subprocess.run([S.ffmpeg_bin(), "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"], capture_output=True, text=True)
    return r.stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("picture", help="picture video (its audio, if any, is ignored)")
    ap.add_argument("mix", help="mix.wav from build_mix.py")
    ap.add_argument("out", help="final mp4 to write")
    ap.add_argument("--encoder", default="aac", help="AAC encoder (default aac; aac_at on macOS if you prefer)")
    a = ap.parse_args(argv)

    x = S.decode(a.mix)
    pk = float(np.abs(x).max())
    fail = []
    if not np.isfinite(x).all() or pk >= 1.0:
        fail.append(f"the mix clips or is not finite (peak {pk:.3f}); nothing is limited, fix the levels")
    out = pathlib.Path(a.out)
    tmp = out.with_name(out.stem + ".encoding.mp4")
    r = subprocess.run([S.ffmpeg_bin(), "-y", "-v", "error", "-i", a.picture, "-i", a.mix, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                        "-c:a", a.encoder, "-b:a", "320k", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg failed:", r.stderr[-500:])
        return 1
    tmp.replace(out)
    pi, po = probe(a.picture), probe(out)
    vi = next(s for s in pi["streams"] if s["codec_type"] == "video")
    vo = next(s for s in po["streams"] if s["codec_type"] == "video")
    ao = next(s for s in po["streams"] if s["codec_type"] == "audio")
    if vi.get("nb_read_frames") != vo.get("nb_read_frames"):
        fail.append(f"frame count changed: {vi.get('nb_read_frames')} -> {vo.get('nb_read_frames')}")
    if packet_md5(a.picture) != packet_md5(out):
        fail.append("the picture stream is not identical to the input picture")
    if (ao.get("sample_rate"), ao.get("channels")) != ("48000", 2):
        fail.append(f"audio is {ao.get('sample_rate')} Hz, {ao.get('channels')} channels, expected 48000 Hz stereo")
    y = S.decode(out)
    n = min(len(x), len(y))
    corr = float(np.corrcoef(x[:n].ravel(), y[:n].ravel())[0, 1])
    if corr < 0.999:
        fail.append(f"the encoded audio does not match mix.wav (correlation {corr:.5f})")
    print(f"{out}: {vo.get('width')}x{vo.get('height')} {vo.get('nb_read_frames')} frames, audio {ao.get('codec_name')} "
          f"{ao.get('sample_rate')} Hz {ao.get('channels')} ch, duration {float(po['format']['duration']):.2f} s, audio correlation {corr:.5f}, mix peak {20 * np.log10(pk + 1e-12):.1f} dBFS")
    for f in fail:
        print("  -", f)
    print("OK" if not fail else "FAIL")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
