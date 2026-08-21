# Convert Impact on USB Exports and Sync-Back

## Question

What does `rbe convert` do to a track that already lives on a rekordbox USB
export, and to the cues and play counts a DJ later adds to that track on hardware?
The desktop trilogy (`../convert-reanalysis-impact/convert-anlz-cue-impact.md` and
its follow-ups) settled that convert is safe for the local library: it rewrites the
`DjmdContent` row, updates the ANLZ `PPTH`, and leaves the grid and cues valid.
This study carries the question onto the USB, where rekordbox keeps a second copy
of the track and its analysis, and where players write changes back.

Every claim is backed by a stage snapshot in `evidence/` produced by
`scripts/export_snapshot.py` and `../shared/scripts/subject_snapshot.py`, run
against the real `export test` playlist on a `D:` drive across three rounds.

## Summary

Converting a track that is already on a USB export breaks that export in two
ways, and both are silent.

1. **Re-export never cleanly updates the exported copy.** An incremental sync
   with no prior device edits does nothing (the USB keeps the pre-conversion
   file). A full re-export, or a sync run after a gig, copies the converted file
   as a **new** track and leaves the original as an orphan on the drive. The
   device playlist follows the new file; the old file becomes silent wasted
   space. rekordbox never removes it.
2. **Sync-back silently drops gig edits on converted tracks.** Cues and play
   counts a DJ adds on the player never reach the collection if the track's
   library file was converted after export. The edit is not duplicated or
   misplaced; it vanishes. This holds on both legacy `export.pdb` players and
   Device Library Plus players.

The practical rule: convert **before** exporting, or re-export **after**
converting so the USB copy matches. Never convert a track that is already on a
USB you will edit on hardware and sync back.

## Method

The subject is a 16-track `export test` playlist exported to a `D:` drive. Four
fixtures carry the measurements; the rest are ballast. Each round drives a real
conversion or a real device edit through the actual apps, then snapshots three
layers: the desktop `master.db` (via `subject_snapshot.py`), and the drive's
`Contents/` audio, `PIONEER/USBANLZ` ANLZ, and device databases (via
`export_snapshot.py`). A backup of `master.db` and the whole `D:` export, taken
before the first conversion, makes every step reversible.

### What Is Readable On The Device

Readable device stores:

- **ANLZ (`PIONEER/USBANLZ`):** read with pyrekordbox `AnlzFile`. Unlike the
  desktop, the device ANLZ carry populated cue lists (`PCO2`/`PCOB`) and a
  device-relative `PPTH`. pyrekordbox cannot parse a player-authored cue list
  (`ConstError`/`PaddingError`), so cue counts come from a raw read of the
  `PCO2` `type` (`u4` at body+12: 0=memory, 1=hot) and `len_cues` (`u2` at
  body+16).
- **`export.pdb` / `exportExt.pdb`:** legacy binary, not parsed. Path strings
  and collection IDs are recoverable by grepping the raw bytes.
- **`exportLibrary.db` (Device Library Plus):** SQLCipher-encrypted. The static,
  machine-independent key is known (`r8gddnr...`, `cipher_compatibility=4`), so
  `export_snapshot.py` decrypts and reads its `content`, `cue`, and `history`
  tables directly. The `content.masterContentId` column equals the desktop
  `DjmdContent.ID`, a convert-stable device-to-collection link.

### Fixtures

| Round | Fixture | ContentID | Role |
| --- | --- | --- | --- |
| 1 | End It | 53013048 | FLAC->AIFF, re-export |
| 1 | 365 featuring shygirl | 121715696 | FLAC->MP3, re-export |
| 1 | Charli - Spring breakers | 54793376 | AIFF 24->WAV, re-export |
| 1 | На такси | 258421826 | control, not converted |
| 2 | End It, 365, На такси | (above) | AIFF baseline, edited on a legacy CDJ, then converted |
| 3 | Hackney Parrot | 268012584 | FLAC, edited on a DB Plus player, then ->AIFF |
| 3 | I Felt Love | 11317782 | FLAC, edited on a DB Plus player, then ->MP3 |
| 3 | Habla Tu Verdad | 140193439 | FLAC, edited, control (not converted) |

## Round 1: Re-Export After Convert

Convert three fixtures in the library, then re-export the playlist to the drive.

**Convert leaves the drive untouched.** After converting, the `D:` snapshot is
byte-identical to baseline: convert rewrites only the desktop library and the
source audio, never the export. On the desktop the current convert updates the
row, the ANLZ `PPTH` (native `?/<name>` form), and `FileSize`, and preserves
every cue. The staleness the older desktop research documented has since been
fixed in the tool.

**An incremental sync with no prior edits does nothing useful.** Re-syncing the
playlist copied no converted audio, refreshed no device ANLZ, and did not
re-point the `export.pdb` track paths (still `.flac`/`.aiff`). Only device-DB
bookkeeping moved. rekordbox matched the exported copy by track identity, judged
it current, and skipped it. The USB still plays the pre-conversion file.

**A full re-export duplicates and orphans.** Forcing a full re-export copied the
converted files as new device tracks (`Contents/` 16->19, three new ANLZ
folders, `export.pdb` grew) while keeping the originals. `export.pdb` then
referenced both `End It.aiff` and `End It.flac`. An on-player check settled the
ambiguity: the playlist lists each converted track **once**, pointing at the new
file, and all three played. The old-format copies are orphaned off-playlist,
which is silent wasted space rather than a visible duplicate. Clean removal
requires deleting the track from the device first, then re-exporting.

## Round 2: Sync-Back On A Legacy PDB Player

A player that writes to `export.pdb`. The fixtures were first converted to AIFF
and re-exported as a CDJ-playable baseline, edited on the CDJ (one memory cue and
a play each on End It, 365, and the control На такси), then reconverted in the
library (End It->WAV, 365->MP3), then synced back.

**Result: converting after export silently drops the sync-back.**

- **На такси (control, not reconverted):** synced cleanly. `DJPlayCount` 1->2,
  and a new `DjmdCue` memory row at the exact position the player wrote.
- **End It (WAV) and 365 (MP3), reconverted after the edit:** nothing. No cue,
  no play count, no duplicate row. The edits vanished.

**The device edit itself succeeded on all three** (the CDJ wrote the memory cue
to the ANLZ, plays to the PDB, and created a `USBMNG.DAT` history index). The
loss is purely on the collection side, and only for the reconverted tracks.

## Round 3: Sync-Back On A Device Library Plus Player

A player that writes to `exportLibrary.db`, with pristine FLAC fixtures. The
edits added one memory cue **and** one hot cue plus a play to each of Hackney
Parrot, I Felt Love, and the control Habla Tu Verdad; then Hackney->AIFF and I
Felt Love->MP3 were converted in the library; then synced back.

**Where the edits landed on the device.** Cues went to the **ANLZ** (`PCO2`:
hot 1->2, mem 0->1 per fixture), exactly like the CDJ. Plays went to the DB Plus
`history_content` table (0->3 rows). The DB Plus `cue` table stayed empty and
`export.pdb` did not change. So even a Device Library Plus player writes cues to
the ANLZ, not to the DB Plus cue table; the DB Plus store received only play
history.

**Result: identical to Round 2, with no split.**

- **Habla Tu Verdad (control, not reconverted):** synced cleanly. `DJPlayCount`
  0->1, and **both** new cues landed (a `Kind=0` memory row and a `Kind=2` hot
  row).
- **Hackney Parrot (AIFF) and I Felt Love (MP3), reconverted:** nothing. Both
  cue types and the play count were dropped; no duplicate row.

The play count dropped for the reconverted tracks **too**, even though it came
from DB Plus `history` keyed by the convert-stable `masterContentId`. Device
Library Plus behaves exactly like the legacy PDB.

**Re-export on this device (confirming Round 1).** A re-sync run after the
sync-back did copy the converted files this time (`Contents/` 16->18, adding
`Hackney Parrot.aiff` and `I Felt Love.mp3` beside the retained `.flac`), and a
following force export added no further copies. The DB Plus `content` re-pointed
to the converted files while the FLAC originals stayed orphaned on disk. Note the
contrast with Round 1: an incremental sync copied the converted files here
because a prior sync-back had primed rekordbox to see the change, where Round 1's
cold sync did nothing.

## The Mechanism

The sync-back failure is **not** a missing link. `export.pdb` contains the
desktop collection ID for every fixture (verified by byte search), and
`exportLibrary.db` stores the same as `masterContentId`. The stable ID is present
even for reconverted tracks, yet their edits are still dropped while the
unconverted control syncs. So rekordbox does not sync by the stable ID alone: it
gates the sync-back on the device copy's format and path still matching the
collection track's **current** file. Convert changes the collection file's
extension, path, and format, so the gate fails and rekordbox skips the whole
track. The gate is per-track, not per-data-type, which is why the play count
(from `history`, keyed by `masterContentId`) is dropped alongside the ANLZ cues.

## Conclusions

For users:

- **Convert before you export.** A track converted before its first export is
  exported in its final format, and nothing downstream breaks.
- **If you convert a track already on a USB, re-export it before the next gig.**
  A full re-export puts the converted file on the drive (leaving an orphan of the
  original, which you can clear by removing the track from the device first).
- **Never rely on syncing back edits made to a track you converted after export.**
  Those cues and play counts will not return to your collection, silently, on any
  device type.

## Reproduction

Read-only unless noted. `export_snapshot.py` and `export_diff.py` are under
`scripts/`; `subject_snapshot.py` and `subject_diff.py` under `../shared/scripts/`.

| Script | Use |
| --- | --- |
| `export_snapshot.py <stage> [drive]` | Drive snapshot: `Contents/` hashes, ANLZ (cues/PPTH/grid), device-DB blobs, and decrypted DB Plus `content`/`cue`/`history` |
| `export_diff.py <a> <b>` | Drive delta: file adds/orphans, ANLZ cue/PPTH changes, device-DB moves, DB Plus content/cue changes |
| `subject_snapshot.py <id> <stage>` | Desktop `master.db` row, cues, and ANLZ for one track |
| `subject_diff.py <id> <a> <b>` | Desktop delta across all three layers |

The DB Plus key and `cipher_compatibility=4` are embedded in `export_snapshot.py`.

## Caveats

- Single trials per fixture. The goal is to characterize behavior and failure
  modes, not to establish a rate.
- Two players tested (one legacy PDB CDJ, one Device Library Plus unit). Firmware
  and device mode vary; the sync-back failure reproduced on both.
- pyrekordbox 0.4.4 cannot parse player-authored cue lists, so device cue counts
  come from a raw `PCO2` read. Its `AnlzFile.save()` also drops the unsupported
  `PVB2` tag, which is a pitfall for any ANLZ rewrite (convert's own `PPTH`
  rewrite avoids it and preserves `PVB2`).
