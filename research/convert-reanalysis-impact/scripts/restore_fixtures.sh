#!/usr/bin/env bash
# Restore the convert-impact fixtures to their clean baseline.
# Copies master.db and the three fixtures' ANLZ folders back from the backup,
# then removes any converted outputs in _ConvertTest, keeping the source WAVs.
# Run only with rekordbox closed.
set -euo pipefail

RB="C:/Users/rbe-test/AppData/Roaming/Pioneer/rekordbox"
BAK="A:/rb-convert-test-backup"
ANLZ="share/PIONEER/USBANLZ"
TESTDIR="A:/Music/_ConvertTest"
FOLDERS="967/6fc9e-2691-42ea-b006-124fe44c354f bf7/1f0c1-704d-46fb-b47d-cefb16a5e3aa 47a/337b6-897a-45a2-a086-f8b88e2f5c40"

cp "$BAK/master.db" "$RB/master.db"
for f in $FOLDERS; do
  rm -rf "$RB/$ANLZ/$f"
  mkdir -p "$RB/$ANLZ/$(dirname "$f")"
  cp -r "$BAK/USBANLZ/$f" "$RB/$ANLZ/$f"
done

# Drop converted outputs, keep the three source WAVs.
find "$TESTDIR" -type f ! -name '*.wav' -delete

echo "Restored master.db + 3 ANLZ folders; cleaned $TESTDIR:"
ls "$TESTDIR"
