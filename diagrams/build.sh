#!/usr/bin/env bash
# Compile every network diagram (*.tex, styles in common.tex) to a 300 dpi PNG
# next to its source. Needs pdflatex (with TikZ) and pdftoppm (poppler).
#
#   cd diagrams && ./build.sh            # all diagrams
#   cd diagrams && ./build.sh braess     # just one
set -euo pipefail
cd "$(dirname "$0")"
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT

names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  for tex in *.tex; do
    [ "$tex" = common.tex ] || names+=("${tex%.tex}")
  done
fi

for name in "${names[@]}"; do
  if ! pdflatex -interaction=nonstopmode -halt-on-error -output-directory "$build" "$name.tex" > "$build/$name.log" 2>&1; then
    echo "pdflatex failed for $name.tex:" >&2
    tail -20 "$build/$name.log" >&2
    exit 1
  fi
  pdftoppm -png -r 300 -singlefile "$build/$name.pdf" "$name"
  echo "built diagrams/$name.png"
done
