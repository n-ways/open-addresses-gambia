#!/bin/sh
# Builds the paper's PDFs from docs/paper.md and its translations (docs/paper.<lang>.md) with pandoc and LaTeX (tectonic).
#   sh docs/paper/build.sh            # every language
# Needs pandoc 3, tectonic and pdftocairo; figures are compiled from docs/figures/*.tex first
# (each <name>-fr.tex gives the French labels of <name>.tex).
set -e
here=$(cd "$(dirname "$0")" && pwd)
docs=$(dirname "$here")
stale() { # $1 figure source: true when its PDF or SVG is missing or older than the source, its base figure or any data file
  out=${1%.tex}.pdf
  [ -e "$out" ] && [ -e "${1%.tex}.svg" ] || return 0
  for dep in "$1" "${1%-fr.tex}.tex" "$docs"/figures/*.dat; do
    [ -e "$dep" ] && [ "$dep" -nt "$out" ] && return 0
  done
  return 1
}
for f in "$docs"/figures/*.tex; do
  [ -e "$f" ] || continue
  b=${f%.tex}
  if stale "$f"; then
    tectonic -X compile --outdir "$docs/figures" "$f" 2>&1 | grep -v "^note:" || true
    pdftocairo -svg "$b.pdf" "$b.svg"
  fi
done
build() { # $1 source, $2 output
  pandoc "$docs/$1" --from markdown+tex_math_dollars+raw_tex --template "$here/template.tex" \
    --lua-filter "$here/figures.lua" --citeproc --bibliography "$here/references.bib" --csl "$here/ieee.csl" \
    -H "$here/style.tex" -H "$here/colours.tex" --resource-path "$docs:$here" --number-sections --toc --pdf-engine=tectonic -o "$docs/$2"
}
base=n-ways-addressing-gambia
for src in "$docs"/paper.md "$docs"/paper.*.md; do
  [ -e "$src" ] || continue
  name=$(basename "$src")
  case $name in paper.md) lang=en ;; *) lang=${name#paper.}; lang=${lang%.md} ;; esac
  build "$name" "$base-$lang.pdf"
done
