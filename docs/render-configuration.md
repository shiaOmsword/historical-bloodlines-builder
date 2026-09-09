# Render configuration (schema version 1)

Rendering settings are immutable per build. With no configuration, the approved
Roboto / Roboto Medium typography and validated orthogonal layout are unchanged.
No historical content or generation/order hints are changed by these settings.

## Quick start on the existing VPS

```bash
cd /opt/apps/historical-bloodlines-builder
# After checking out the feature branch and pulling its code:
cp config/render.plus2.yaml data/render.yaml
make rebuild-bot
make up-proxy
```

The existing Compose bind mount exposes `data/render.yaml` as `/data/render.yaml`.
After the initial code/dependency rebuild, changing this file affects the next
uploaded workbook without another rebuild or restart:

```bash
cp config/render.plus3.yaml data/render.yaml
# Restore the approved baseline explicitly:
cp config/render.default.yaml data/render.yaml
```

The bot reads the file once per workbook, before EPS, PNG and PDF generation. A
change during a job cannot mix styles inside its bundle. The publisher ZIP also
contains `render-settings.yaml`: a standalone snapshot of the settings used.
An injected builder keeps its explicit configuration rather than reloading it.
The desktop launcher reads settings when its builder is created: restart it after
editing the file. It is not the bot's per-request lifecycle.

## CLI and discovery

```bash
poetry run bloodlines -i book.xlsx -o result.pdf --render-config config/render.plus2.yaml
# Override only PDF paper size:
poetry run bloodlines -i book.xlsx -o result.pdf --render-config config/render.plus3.yaml --paper a4
```

Precedence: explicit `--render-config` (or Python `render_config_path`) >
`BLOODLINES_RENDER_CONFIG` > `$BLOODLINES_DATA_DIR/render.yaml` > `./render.yaml` >
built-in defaults. Relative paths resolve from the working directory. Discovery
selects ONE file; it does not merge multiple files. Within that file, omitted
fields use built-in defaults. A missing explicit/environment file is an error,
not a silent fallback. The local root and data YAML files are gitignored.

```yaml
version: 1
typography:
  font_size_pt: 15.2
  line_height_pt: null
  title_font_size_pt: 21
  note_font_size_pt: 11
layout:
  person_gap_pt: 34
  component_gap_pt: 22
  layer_gap_pt: 30
  page_margin_x_pt: 18
  page_margin_y_pt: 16
  min_page_width_pt: 560
  max_text_line: 20
  max_name_line: 16
pdf:
  page_format: a5
```

`font_size_pt` covers person names, titles and dates. `title_font_size_pt` is the
heading of the whole table; `note_font_size_pt` is for footnotes. Font families
are intentionally not configurable in version 1. The two wrap limits are
character counts, not points. All other dimensions above are native points.
`pdf.page_format` affects PDF only, not native EPS/SVG/PNG canvas dimensions.

Automatic leading follows `font_size_pt * 15 / 13.2`, rounded UP to an integer.
Explicit fractional leading is also rounded up: Graphviz HTML rows use integer
heights, so the layout's measured boxes must use exactly the same height.
Baseline / +2 / +3 body sizes are 13.2 / 15.2 / 16.2 pt, with 15 / 18 / 19 pt
leading. The experiment presets also add 2 or 3 pt to headings and footnotes.

Unknown keys, duplicate keys, unsupported schema versions, unsafe YAML tags,
aliases, invalid types, non-finite numbers and out-of-range settings are rejected.
The file size is limited to 64 KiB. A comment-only file uses defaults. Routing
validation remains mandatory; a setting is not a guarantee that every workbook
can be laid out with those constraints. Nothing disables the collision checks.

## Native points are not the final printed point size

PDF placement uniformly scales a native diagram to fit the selected paper:

```text
scale = min(available_width / native_width,
            available_height / native_height,
            max_upscale)
printed_font_size = native_font_size * scale
```

Larger labels enlarge the diagram too. Therefore +3 native pt does NOT mean +3
printed pt on A5. Increasing paper size or revising the layout is a separate
choice. No non-uniform X/Y stretching is introduced by this feature.

## Repeatable comparison

```bash
poetry run python scripts/compare_render_configs.py book.xlsx --output-dir comparison-01 --publisher
```

The output directory must not already exist. The script runs the three included
presets, retains native PDFs and settings snapshots, makes a complete PDF book
only for variants with no failed sheets, and writes `report.json` with input and
config hashes, runtime version, native dimensions, scale, final font size,
geometry issue counts, warnings and errors. `--publisher` additionally writes
outlined EPS and PNG previews and checks EPS for unexpected raster content.
Custom presets can be supplied with repeated `--config path.yaml` arguments.
The script returns a nonzero exit status if any sheet fails. PNG is a separate
renderer preview, not a rasterization of the EPS importer used by the publisher.

The local acceptance run used the supplied 14-sheet workbook (SHA256
`2b7b3cdf450e3cff66edebe5257fd62fc2c0a66601285cfd3cdf56a4c79c9991`). All 42
sheet/preset combinations rendered as PDF and outlined EPS with no reported
routing conflicts. On that run, +2 yielded approximately +0.10 to +0.47 printed
pt on A5, and +3 yielded +0.25 to +0.82 pt. The default PDF raster matched the
unmodified `c0dd7f2` baseline in the same runtime. This is not a claim of binary
identity with the previously uploaded PDF or of publisher approval. The actual
workbook and generated documents are not checked into this repository.
