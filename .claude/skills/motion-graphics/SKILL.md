---
name: "motion-graphics"
description: "Add cached official-asset and product research preflight before reference selection and build authorization."
---

# Motion Graphics for AI Videos

Use with `remotion-best-practices` and `cinematic-camera`. This skill owns intake, research, authentic assets, reference selection, visual quality, and delivery authorization.

## Inside the video editor (read first)

When this skill makes graphics for a Reel being edited in this project, the `style` skill's approved coverage map decides what gets built. Build only the rows coded IN BIG, IN SMALL or OUT, one row at a time, starting with the hook. Format then comes from the row's mode, not from the intake question:

| Mode | Render | Where the important content goes |
| --- | --- | --- |
| IN BIG | Full 1080x1920 frame. The graphic lives in the top 1080x960 stage; it is solid to y770 and fades into the background surface by y940 on a smoothstep curve. Nothing but background below y940. The speaker's panel is not in the asset; the editor lays it on top. | x120 to 960, y250 to 760 |
| IN SMALL | Full 1080x1920 frame, background full-frame behind everything. | x120 to 960, y200 to 1172 |
| OUT | Full 1080x1920 frame. | x120 to 960 |

Exact numbers: `.claude/skills/style/references/layout.json`. Ask the surface question once per video, and use that one surface for every graphic and as the editor's background so the whole video is one seamless world.

Also:
- **Use real logos and real screenshots.** A product page, a repo, a dashboard: capture the real thing (supplied, or the official public page) and animate it. Generic AI animation is exactly what this skill exists to avoid.
- **Write the action frames in a comment at the top of each composition** (for example `// f12 card lands, f40 cursor clicks "Run", f58 zoom fastest frame`). The editor pins those actions to the spoken words, and the sound-effects skill puts a sound on each one.
- Before showing any graphic, run `.venv/bin/python .claude/skills/style/scripts/check_side_crop.py out/candidate.mp4`. It must pass.

## Hard execution contract

Every build must pass `scripts/motion-gate.mjs`.

Common paths:

- Claude Code: `.claude/skills/motion-graphics/scripts/motion-gate.mjs`
- Other agents: `.agents/skills/motion-graphics/scripts/motion-gate.mjs`

Do not write composition code until the script prints `BUILD AUTHORIZED`. Do not deliver a render until it prints `DELIVERY AUTHORIZED`. A failed command is a hard stop.

## Stage 1: concise intake

Ask only for missing choices:

1. Format: **4:3 half-screen Instagram insert (1440×1080)** or **9:16 full-screen Instagram (1080×1920)**. Use 16:9 only when explicitly requested.
2. Surface: **warm light**, **clean dark**, **light grid**, or **dark grid**.
3. Exact script beat, duration, named products, verified claims, and supplied assets.

Never silently default to dark. If the user delegates surface choice, use warm light.

## Stage 2: research and authentic assets

Read `references/research-and-assets.md` and `references/logo-library.md`.

Run the smallest useful research course before concept work:

- Supplied user assets are authoritative. Use them exactly; never redraw or replace them.
- For common products, copy a suitable bundled logo from `assets/logos/` into the project and retain its provenance.
- If missing, inspect 1–3 authoritative pages: official brand kit/homepage, official docs/product page, then a reputable curated icon source.
- Prefer transparent SVG. Never use screenshots of logos, search-result thumbnails, baked checker/gray backgrounds, unofficial recreations, or hotlinked remote assets.
- For a dashboard/product UI, acquire a real supplied screenshot/recording or an official public product/docs screenshot. If none exists, ask; do not invent a dashboard.
- Research visible structure, terminology, brand color, and the exact action/state relevant to the beat. Do not copy unsupported metrics, private information, or claims.
- Cache assets and notes under `.motion/research/`. Reuse a cache hit when product, sources, asset hashes, and reference mechanism are unchanged.

Choose only the visual mode the beat needs: `logo-system`, `product-ui`, `terminal`, `editorial`, or `abstract`. Do not force a newsletter, dashboard, terminal, or elaborate camera move into every graphic.

Write `.motion/research-brief.md` with these headings:

```markdown
## Product or concept
## Authoritative sources
## Real visual language
## Closest approved mechanism
## Motion plan
## Avoid
```

Then run:

```bash
node <skill-dir>/scripts/motion-gate.mjs research \
  --project . \
  --research-mode authentic \
  --visual-mode product-ui \
  --product "Slack" \
  --reference kickbacks-same-run-editor \
  --brief .motion/research-brief.md \
  --source https://slack.com/ \
  --logo public/research/slack.svg \
  --surface public/research/slack-dashboard.png
```

For unnamed conceptual work, use `--research-mode abstract --visual-mode abstract`; the brief and approved-reference comparison still apply, but unnecessary web/logo research does not.

## Stage 3: verified reference preflight

Read `references/approved-references.md`. Select by story mechanism, not color. A new concept is allowed when it is more specific to the request, but it must explicitly inherit camera grammar, scale, restraint, and causal motion from the closest approved mechanism. Combine at most two mechanisms.

Run:

```bash
node <skill-dir>/scripts/motion-gate.mjs init \
  --project . \
  --research .motion/research-manifest.json \
  --format 9:16 \
  --background warm-light \
  --claim-source user \
  --beat "Exact visual idea being supported" \
  --duration 6
```

`init` revalidates research/assets, verifies the bundled approved MP4/contact sheet by SHA-256, and writes `.motion/render-brief.json`.

Inspect the actual bundled MP4/contact sheet and the researched product evidence. Write `.motion/reference-observations.md` with:

```markdown
## Composition
## Camera
## Identity
## Research match
## Anti-pattern
```

Then run:

```bash
node <skill-dir>/scripts/motion-gate.mjs inspect \
  --project . \
  --observations .motion/reference-observations.md
```

Only `BUILD AUTHORIZED` permits implementation.

## Stage 4: build

Use the researched identity and the selected reference’s causal mechanism. The result should feel specific on the first pass, not like a template waiting for corrective prompting.

Hard rules:

- Zero neon, glow, bloom, luminous edges, colored shadows, gradient orbs/washes, cyan-purple gradients, glassmorphism, cyberpunk lighting, or vibe-coded AI styling.
- No generic receipt, invoice, dossier, clipboard, floating card, barcode, rubber stamp, certificate, pricing card, fake dashboard, or disconnected card-grid fallback.
- Realistic dashboards are encouraged only when grounded in supplied or authoritative product evidence. Recreate visible structure faithfully; never invent metrics, claims, controls, or product states.
- No invented UI, logos, prices, ranks, engagement, serials, or proof.
- No redundant narration text. Real data, product UI, commands, code, filenames, and short structural labels are allowed.
- Motion must reveal causality, scale, replacement, navigation, or state change. It may be restrained when a logo swap or authentic UI action communicates the beat clearly.
- A static centered object with rows appearing plus a slow zoom is not cinematic execution.
- Use fewer, larger focal objects. Keep the current action centered, fully visible, and readable at destination size.
- Dark scenes are opt-in. Dark means neutral near-black with flat accents, never illuminated panels.

Read `references/rejected-patterns.md` before concept selection.

## Stage 5: candidate evidence

Render the candidate. Generate a three-frame contact sheet and `ffprobe` JSON. Example for six seconds:

```bash
mkdir -p .motion
ffmpeg -y -hide_banner -loglevel error -i out/candidate.mp4 \
  -vf "fps=3/6,scale=480:-1,tile=3x1:padding=12:margin=12:color=white" \
  -frames:v 1 .motion/candidate-contact-sheet.jpg
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height:format=duration -of json \
  out/candidate.mp4 > .motion/candidate-probe.json
```

Then run:

```bash
node <skill-dir>/scripts/motion-gate.mjs candidate \
  --project . \
  --render out/candidate.mp4 \
  --contact-sheet .motion/candidate-contact-sheet.jpg \
  --probe .motion/candidate-probe.json
```

## Stage 6: independent visual critic

The builder cannot grade its own work. Start a separate clean critic/subagent with:

- `references/visual-critic.md`
- research brief/manifest and authentic assets
- selected approved MP4/contact sheet
- candidate MP4/contact sheet
- `.motion/render-brief.json`

The critic inspects actual media and returns JSON matching `templates/critic-output.example.json`. If independent review cannot run, stop; never self-approve.

## Stage 7: delivery gate

```bash
node <skill-dir>/scripts/motion-gate.mjs qa \
  --project . \
  --critic .motion/critic.json
```

The gate rejects hard failures, any category below 8/10, average below 8.5, modified/missing research or evidence, or non-independent review. Revise until `DELIVERY AUTHORIZED`.

## Technical and delivery rules

- Drive motion with `useCurrentFrame()`, `spring()`, and `interpolate()`; no CSS animation.
- Use hold → travel → hold when travel helps. Action completes during holds.
- End with a stable editor hold.
- Typecheck or run the smallest meaningful build validation.
- Deliver MP4 with exact dimensions, duration, render command, and editor placement note only after authorization.
