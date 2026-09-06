#!/usr/bin/env bash
# Restore the GIG MUSIC test library to a captured backup, so each arm of the
# removal study starts from the same state.
#
#   research/remove-track-impact/scripts/restore.sh [backup-name]
#
# Backup name defaults to "prepared", the post-fixture-prep state every arm
# diffs against. Use "pre-prep" for the state before any cues were set.
#
# Restores three things, because a removal destroys on-disk state that copying
# the database back does not return: master.db, the subjects' analysis
# directories, and the staged fixture audio the subject rows point at.
set -euo pipefail

BACKUP_NAME="${1:-prepared}"
BACKUP_ROOT="$HOME/rb-remove-test-backup/$BACKUP_NAME"
LIBRARY="/Volumes/GIG MUSIC/PIONEER/Master"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STAGING="/private/tmp/rbe-remove-fixtures"

if pgrep -x rekordbox >/dev/null; then
  echo "rekordbox is running; quit it before restoring." >&2
  exit 1
fi
if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "no backup at $BACKUP_ROOT" >&2
  exit 1
fi

cp "$BACKUP_ROOT/master.db" "$LIBRARY/master.db"
rm -f "$LIBRARY/master.db-wal" "$LIBRARY/master.db-shm"

if [[ -d "$BACKUP_ROOT/anlz" ]]; then
  # Copy each subject directory back by name rather than clobbering USBANLZ,
  # so an unrelated track's analysis is never touched.
  while IFS= read -r dir; do
    rel="${dir#"$BACKUP_ROOT/anlz/"}"
    mkdir -p "$LIBRARY/share/PIONEER/USBANLZ/$(dirname "$rel")"
    rm -rf "${LIBRARY:?}/share/PIONEER/USBANLZ/$rel"
    cp -R "$dir" "$LIBRARY/share/PIONEER/USBANLZ/$rel"
  done < <(find "$BACKUP_ROOT/anlz" -mindepth 2 -maxdepth 2 -type d)
fi

if [[ -d "$BACKUP_ROOT/artwork" ]]; then
  # Artwork is the second per-track on-disk artifact, keyed by the same content
  # UUID as the analysis directory and restored the same way.
  while IFS= read -r dir; do
    rel="${dir#"$BACKUP_ROOT/artwork/"}"
    mkdir -p "$LIBRARY/share/PIONEER/Artwork/$(dirname "$rel")"
    rm -rf "${LIBRARY:?}/share/PIONEER/Artwork/$rel"
    cp -R "$dir" "$LIBRARY/share/PIONEER/Artwork/$rel"
  done < <(find "$BACKUP_ROOT/artwork" -mindepth 2 -maxdepth 2 -type d)
fi

# Rebuild the fixture copies rather than restoring them: build_fixtures.py is
# idempotent and re-derives each subject from its source file in the collection,
# so an arm that deleted one gets a byte-identical replacement.
uv run --project "$REPO_ROOT" python \
  "$REPO_ROOT/research/remove-track-impact/scripts/build_fixtures.py" >/dev/null

echo "restored $BACKUP_NAME"
echo "  master.db  $(shasum "$LIBRARY/master.db" | cut -d' ' -f1)"
echo "  anlz dirs  $(find "$BACKUP_ROOT/anlz" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l | tr -d ' ')"
echo "  artwork    $(find "$BACKUP_ROOT/artwork" -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l | tr -d ' ') dir(s)"
echo "  fixtures   $(ls "$STAGING" | wc -l | tr -d ' ') file(s) rebuilt"
