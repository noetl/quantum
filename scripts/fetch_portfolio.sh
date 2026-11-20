#!/usr/bin/env bash
# Fetch the external portfolio circuits named in portfolio/candidates.json
# into a git-ignored folder. Needs the Kaggle CLI and an API token. The
# files are other authors' Apache-2.0/CC0 work: see portfolio/CREDITS.md.
# The pipeline checks every file's sha256 against the manifest.
set -euo pipefail
ROOT="$(CDPATH="" cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-${ROOT}/candidates}"
REF="alexchilton/28-24-lb-which-circuits-survive-private-salt"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
kaggle kernels output "$REF" -p "$TMP" --file-pattern '^submission\.zip$'
python3 -I - "$TMP/submission.zip" "$DEST" <<'PY'
import sys, zipfile, pathlib, shutil
zpath, dest = sys.argv[1], pathlib.Path(sys.argv[2])
layout = {"invsqrt.kmb": "invsqrt/acc7b9c8/invsqrt.kmb", "dqi.kmb": "dqi/f6b555a6/dqi.kmb"}
with zipfile.ZipFile(zpath) as z:
    for name in z.namelist():
        if name.startswith("/") or ".." in name.split("/"):
            raise SystemExit(f"unsafe member {name}")
        target = layout.get(name) or (f"dfthcsos/e6233e86/{name}" if name.startswith("dfthcsos/") else None)
        if target is None:
            continue
        out = dest / target
        out.parent.mkdir(parents=True, exist_ok=True)
        with z.open(name) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
        print(out)
PY
