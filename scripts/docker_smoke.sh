#!/usr/bin/env sh
set -eu

mkdir -p data/input data/output
cp examples/input.example.xlsx data/input/smoke.xlsx
rm -rf data/output/smoke data/output/smoke.pdf

docker compose build renderer

docker compose run --rm renderer \
  -i /data/input/smoke.xlsx \
  -o /data/output/smoke.eps

docker compose run --rm renderer \
  -i /data/input/smoke.xlsx \
  -o /data/output/smoke.pdf

EPS_FILE=$(find data/output/smoke -type f -name '*.eps' -print -quit)
PREVIEW_FILE=$(find data/output/smoke -type f -name '*.preview.png' -print -quit)

if [ -z "${EPS_FILE}" ] || [ ! -s "${EPS_FILE}" ]; then
  echo "Docker smoke failed: EPS was not generated" >&2
  exit 1
fi

if [ -z "${PREVIEW_FILE}" ] || [ ! -s "${PREVIEW_FILE}" ]; then
  echo "Docker smoke failed: preview PNG was not generated" >&2
  exit 1
fi

if [ ! -s data/output/smoke.pdf ]; then
  echo "Docker smoke failed: PDF was not generated" >&2
  exit 1
fi

echo "Docker renderer smoke passed"
echo "EPS: ${EPS_FILE}"
echo "Preview: ${PREVIEW_FILE}"
echo "PDF: data/output/smoke.pdf"
