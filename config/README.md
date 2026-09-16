# Render YAML and font-size experiments

See [the configuration guide](../docs/render-configuration.md).

Copy `render.plus2.yaml` or `render.plus3.yaml` to `../data/render.yaml`
for the Docker bot, or pass `--render-config` to the CLI.
`render.default.yaml` restores the approved baseline.

For the 2026-09-16 publisher review round, `render.publisher-review.yaml` keeps
+2 body/title typography, increases footnotes to the body size, and reduces the
spouse gap from 34 pt to 28 pt. This profile is intentionally separate from the
stable `plus2` preset so the earlier comparison remains reproducible.
