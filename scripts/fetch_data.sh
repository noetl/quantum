#!/usr/bin/env bash
# Document and, only with --download, fetch the Kaggle competition data
# into the git-ignored data/ directory. This script does not commit anything.
set -euo pipefail

COMPETITION="google-verifiable-quantum-circuit-compilation"
ROOT="$(CDPATH="" cd "$(dirname "$0")/.." && pwd)"
DEST="${ROOT}/data"
DOWNLOAD=0

usage() {
  cat <<EOF
Fetch the VQCC competition data into a git-ignored folder.

The Kaggle data page requires a login, and the dataset is about 1 GB and
license-restricted. Do not commit data/, submissions/, or kickmix binaries.

Setup (once):
  pip install kaggle
  # Accept the competition rules in the browser while logged in:
  #   https://www.kaggle.com/competitions/${COMPETITION}/rules
  # Create an API token from Kaggle Account -> Settings -> API -> Create New Token.
  # Save it as ~/.kaggle/kaggle.json with mode 600:
  #   mkdir -p ~/.kaggle && chmod 600 ~/.kaggle/kaggle.json

What this downloads (as described on the team hub, not re-listed from Kaggle
because that page was rate-limited here):
  the competition zip, which the hub says is 1.04 GB and 34 files, including
  the paper PDF, sample_submission/, verifiers/, and kickmix/kickmix.so.

Usage:
  $(basename "$0")                 print these steps and do not download
  $(basename "$0") --download      run the Kaggle CLI into ${DEST}
  $(basename "$0") --dest DIR      override the destination (still not committed)

After a download, unzip lands inside the destination. Confirm verifiers/ is
present, then run task checks from the repository root. Leave the files
untracked. .gitignore already excludes /data/, /submissions/, and **/*.so.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --download)
      DOWNLOAD=1
      shift
      ;;
    --dest)
      DEST="${2:-}"
      if [[ -z "$DEST" ]]; then
        echo "error: --dest needs a directory" >&2
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

usage

if [[ "$DOWNLOAD" -ne 1 ]]; then
  echo
  echo "Not downloading. Re-run with --download after the rules are accepted."
  exit 0
fi

if ! command -v kaggle >/dev/null 2>&1; then
  echo "error: kaggle CLI not found. Install it with: pip install kaggle" >&2
  exit 1
fi

mkdir -p "$DEST"
echo "Downloading ${COMPETITION} into ${DEST}"
kaggle competitions download -c "$COMPETITION" -p "$DEST"

shopt -s nullglob
zips=("$DEST"/*.zip)
shopt -u nullglob
if [[ ${#zips[@]} -eq 0 ]]; then
  echo "error: download finished but no zip appeared in ${DEST}" >&2
  exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
  echo "Download saved. unzip is not installed; extract ${zips[*]} into ${DEST} yourself." >&2
  exit 0
fi

for zip in "${zips[@]}"; do
  echo "Extracting ${zip}"
  unzip -n "$zip" -d "$DEST"
done

echo "Done. ${DEST} is git-ignored. Do not commit it."
echo "Next: look for verifiers/ and kickmix/kickmix.so under ${DEST}."
