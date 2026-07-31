#!/usr/bin/env bash
# Restore the course videos from videos.zip into their original locations.
#
# videos.zip is not in git (too large) — it lives in Google Drive:
#   https://drive.google.com/drive/u/0/folders/1h1YzLhJd_YppYG5d6UMpG8yZN69pcY3r
# Download it to the repo root, then run this script.
#
# Paths inside the archive are relative to the repo root and reflect the
# pre-2026-07-31 layout, so extraction recreates edu/videos/,
# edu/resources/**/videos/ and edu/start_here/ as they were then. Two of those
# have since moved under edu/123sequence/ — extracting recreates them at their
# OLD paths as duplicates. Delete the strays afterwards, or extract selectively:
#
#   unzip videos.zip 'edu/resources/*' -d .
#
# The archive also predates the three newest videos in edu/123sequence/videos/,
# which it does NOT contain. Rebuild it before relying on it as a backup.
#
# Safe to re-run: existing files are kept unless --force is passed.
#
#   ./unzip_videos.sh            # extract, skip files already present
#   ./unzip_videos.sh --force    # overwrite existing files
#   ./unzip_videos.sh --list     # show archive contents, extract nothing

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="$REPO_ROOT/videos.zip"

if ! command -v unzip >/dev/null 2>&1; then
  echo "error: 'unzip' not found on PATH" >&2
  exit 1
fi

if [[ ! -f "$ARCHIVE" ]]; then
  cat >&2 <<EOF

videos.zip not found in $REPO_ROOT

The video archive (~1.4 GB) is too large for git and is kept in Google Drive:

  https://drive.google.com/drive/u/0/folders/1h1YzLhJd_YppYG5d6UMpG8yZN69pcY3r

Download videos.zip from that folder, place it at:

  $ARCHIVE

then re-run this script:

  ./$(basename "${BASH_SOURCE[0]}")

EOF
  exit 1
fi

case "${1:-}" in
  --list|-l)
    unzip -l "$ARCHIVE"
    exit 0
    ;;
  --force|-f)
    MODE=-o          # overwrite without prompting
    ;;
  "")
    MODE=-n          # never overwrite existing files
    ;;
  *)
    echo "usage: $(basename "$0") [--force|--list]" >&2
    exit 2
    ;;
esac

echo "Extracting $(basename "$ARCHIVE") into $REPO_ROOT ..."
unzip -q "$MODE" "$ARCHIVE" -d "$REPO_ROOT"
echo "Done. $(unzip -l "$ARCHIVE" | tail -1 | awk '{print $2}') files restored."
