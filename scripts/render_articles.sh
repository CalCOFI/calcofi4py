#!/usr/bin/env bash
# Pre-render the articles — the Python version of R's *pre-computed vignette*.
#
# Each articles/*.qmd is converted with jupytext and EXECUTED with nbconvert against the
# private PostgreSQL database through YOUR SSH tunnel and ~/.pgpass; the executed notebook
# (outputs stored) lands in docs/articles/, which the docs workflow publishes as-is via
# mkdocs-jupyter (execute: false). GitHub Pages therefore needs no database credentials,
# and the site build never touches the server.
#
# Why not `quarto render --to ipynb`: Quarto routes outputs through pandoc, which truncates
# pandas' <div><style>…<table> HTML to its closing </div> — every DataFrame vanished.
#
# Needs: a server account (https://calcofi.io/docs/server-access.html) and, in the Python
# you run this with: calcofi4py[viz] jupytext nbconvert ipykernel  (pip install -e ".[dev]").
#   scripts/render_articles.sh && git add docs/articles && git commit -m "articles: re-rendered"
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-$(command -v python3)}
PY="$(cd "$(dirname "$PY")" 2>/dev/null && pwd)/$(basename "$PY")"   # absolute, cd-proof
export PATH="$(dirname "$PY"):$PATH"   # the kernelspec's argv says `python`: make it THIS python
# make THIS interpreter's ipykernel the `python3` kernel: a user-level kernelspec
# (~/Library/Jupyter/kernels/python3) would otherwise take precedence and run the wrong Python
export JUPYTER_DATA_DIR="$("$PY" -c 'import sys; print(sys.prefix)')/share/jupyter"
[ -f "$JUPYTER_DATA_DIR/kernels/python3/kernel.json" ] || "$PY" -m ipykernel install --prefix "$("$PY" -c 'import sys; print(sys.prefix)')" --name python3 >/dev/null
mkdir -p docs/articles
for qmd in articles/*.qmd; do
  name=$(basename "${qmd%.qmd}")
  out="docs/articles/$name.ipynb"
  "$PY" -m jupytext --to ipynb --quiet "$qmd" -o "$out"
  "$PY" -m jupyter nbconvert --to notebook --execute --inplace --log-level=WARN \
      --ExecutePreprocessor.kernel_name=python3 --ExecutePreprocessor.timeout=1800 \
      --ExecutePreprocessor.cwd="docs/articles" "$out"        # a failing cell fails the script (set -e)
  "$PY" - "$out" <<'PYEOF'
import json, sys
p = sys.argv[1]; nb = json.load(open(p))
nb["metadata"].pop("widgets", None)                      # no widget state in the published notebook
for c in nb["cells"]:
    c.get("metadata", {}).pop("execution", None)         # no per-cell timestamps churning the diff
    if c["cell_type"] == "code" and any(l.startswith("#| echo: false") for l in c["source"]):
        c["metadata"]["tags"] = ["hide-input"]           # mkdocs-jupyter hides the source of tagged cells
        c["source"] = [l for l in c["source"] if not l.startswith("#| ")]
json.dump(nb, open(p, "w"), indent=1, ensure_ascii=False)
errs = [o for c in nb["cells"] if c["cell_type"] == "code" for o in c.get("outputs", []) if o.get("output_type") == "error"]
if errs: sys.exit(f"{p}: {len(errs)} cell(s) errored — {errs[0].get('ename')}: {errs[0].get('evalue')}")
if not any(c.get("outputs") for c in nb["cells"] if c["cell_type"] == "code"):
    sys.exit(f"{p}: no cell produced output — the notebook did not execute")
print("rendered", p, "-", sum(c["cell_type"] == "code" for c in nb["cells"]), "code cells, no errors")
PYEOF
done
