# Setup prompt

Make a folder called **AI Video Editor**, open Claude Code in it, and paste everything in the box below.

```text
Set up this folder as my AI video editor. Do every step yourself and tell me only if something needs me.

1. Clone https://github.com/Liamrjohnston/ai-video-editor into this folder (into the current folder itself, not a subfolder). If the folder already has files, clone to a temp folder and copy everything in, including the hidden .claude folder, without overwriting my files.
2. Make sure these are installed, installing anything missing (on a Mac use Homebrew; ask me before installing Homebrew itself):
   - ffmpeg and ffprobe
   - Node.js 20 or newer
   - Python 3.10 or newer
3. Make a Python virtual environment at .venv in this folder and install requirements.txt into it. From now on, run every Python script in this project with .venv/bin/python.
4. Make a Remotion project for the graphics in ./remotion with: npx create-video@latest --yes --blank --no-tailwind remotion
   Then install the official Remotion skill into this project: npx -y skills add remotion-dev/skills -a claude-code -y
5. Download the free Departure Mono caption font (SIL Open Font License) from its official release, https://github.com/rektdeckard/departure-mono/releases/latest (the DepartureMono zip), and put DepartureMono-Regular.woff2 in remotion/public/fonts/. Then copy .claude/skills/style/references/Captions.tsx into remotion/src/.
6. Make the folders footage/ and edits/.
7. Check it all works:
   - .venv/bin/python .claude/skills/sound-effects/scripts/bank.py verify  (must say all 45 sounds verified)
   - bash tests/test_sound.sh and bash tests/test_cut_style.sh  (must pass)
   - ffmpeg -version and node -v
8. Tell me in plain words what got installed, that the four skills are ready (cut, style, sound-effects, motion-graphics), and that I just drop my raw video into footage/ and say "edit this".
```

When it's done, drop your raw talking-head footage into `footage/` and tell Claude to edit it. If something's off, just tell it what to change.
