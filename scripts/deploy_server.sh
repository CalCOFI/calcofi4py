#!/usr/bin/env bash
# Upgrade calcofi4py on the CalCOFI server — inside the rstudio container's /opt/venv, the
# Python that RStudio's reticulate console uses (rstudio.calcofi.io is where the CTD team
# runs the examples). Run after EVERY version bump pushed to main: the server image bakes
# the package only at build time (server/rstudio/Dockerfile), so between rebuilds this is
# the only thing that updates it.
#   scripts/deploy_server.sh            # main
#   scripts/deploy_server.sh v0.3.5     # a tag / branch / sha
# Needs the `calcofi` SSH alias (https://calcofi.io/docs/server-access.html) with sudo-less
# docker exec rights (bebest).
set -euo pipefail
REF=${1:-main}
ssh calcofi "docker exec rstudio /opt/venv/bin/pip install --no-cache-dir --upgrade --quiet \
    \"calcofi4py[viz] @ git+https://github.com/CalCOFI/calcofi4py@${REF}\" \
  && docker exec rstudio /opt/venv/bin/python -c 'import calcofi4py as cc; print(\"server calcofi4py\", cc.__version__)'"
echo "note: an open RStudio session keeps the previously imported module — Session > Restart R to pick this up"
