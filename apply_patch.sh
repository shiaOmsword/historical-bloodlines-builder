#!/usr/bin/env sh
set -eu
repo_root="${1:-.}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
patch_path="$script_dir/historical-bloodlines-ghostscript-outlines.patch"
cd "$repo_root"
git apply --check "$patch_path"
git apply "$patch_path"
printf '%s\n' 'Patch applied successfully.' 'Next: poetry run pytest -q'
