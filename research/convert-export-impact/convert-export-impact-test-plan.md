# Convert Impact on USB Export and Sync-Back: Test Plan

## Question

The convert-and-analysis trilogy settled what a `convert` run does to the desktop
library: it rewrites only the `DjmdContent` row, leaves every ANLZ file and
`DjmdCue` row untouched, and the kept analysis stays time-valid. Those studies
stopped at the desktop. This plan carries the question onto a USB export, where
rekordbox keeps a second copy of the track, its cues, and its analysis, and where
DJ equipment can write changes back. The desktop studies are under
`../convert-reanalysis-impact/`.

The subject is a real export already on the `D:` drive: the `export test`
playlist, exported from the local rekordbox 6 library. Every step is reversible
from a backup taken before the first conversion.

## Scope and Goals

Two rounds, run in order, because the second depends on the export state the
first perturbs. Each round answers one question a USB user actually faces.

**Round 1: re-export after convert.** Convert a subset of the exported tracks in
the desktop library, then re-export the `export test` playlist to the same drive.
The question is what rekordbox does when the file it exported before now has a
different format, path, and size. Does it recognize the track as the same one and
update the exported copy in place, does it treat the converted file as new and
duplicate it, or does it believe the export is already current and copy nothing?

**Round 2: sync-back after convert.** Reproduce the common gig sequence out of
order on purpose: play tracks and add cues on the player, convert the same tracks
in the desktop library, then sync the drive's changes back into the collection.
The question is what happens to `master.db` when a device edit arrives for a
track whose file has since been converted. Does the play count and the new cue
land on the correct, now-converted collection track, does the edit drop, or does
the sync create a duplicate?

A control track that is exported and edited on the player but never converted
runs through both rounds, so any breakage is attributable to convert rather than
to the export or sync mechanism itself.

## The Export, As It Exists on D:

The drive already carries a complete rekordbox 6 export with three stores, which
is what makes it a usable subject:

- `Contents/` holds the copied audio, foldered by artist and album, each file
  keeping its source extension.
- `PIONEER/USBANLZ/<PXXX>/<id>/` holds one ANLZ set per track. Unlike the desktop
  ANLZ, the device copies carry populated cue lists (`PCO2`/`PCOB`) and a
  device-relative `PPTH` that includes the extension, for example
  `/Contents/Blue Hawaii/Under 1 House/02. ....flac`.
- `PIONEER/rekordbox/` holds the device databases: `export.pdb` and
  `exportExt.pdb` (the legacy binary format) plus `exportLibrary.db` with its WAL
  and SHM (the encrypted Device Library Plus store).

Convert changes the desktop file and the desktop row. None of these device
stores updates until rekordbox re-exports or syncs, which is exactly the gap
under test.

## Tooling and Instrumentation

What is readable without new heavy tooling decides the evidence surface:

- **ANLZ is fully readable.** pyrekordbox's `AnlzFile` parses the device ANLZ,
  including the populated cue lists, the device `PPTH`, the beat grid, and the
  waveforms. This is the richest device-side evidence and it costs nothing. On
  the desktop these cue lists were empty; on the drive they hold real cues, so
  the export is where cue survival becomes observable in the ANLZ layer.
- **The legacy PDB is opaque here.** `export.pdb` is the page-based binary
  format. pyrekordbox does not parse it and ships no kaitai reader.
- **The Device Library Plus store is encrypted with a key we do not hold.** The
  master.db SQLCipher key (`402fd482...`, 64 hex, obtained through pyrekordbox's
  `deobfuscate(BLOB)`) fails the HMAC check on page 1 of `exportLibrary.db` under
  every cipher-compatibility variant. Device Library Plus uses a different key,
  and recovering it is a separate reverse-engineering effort outside this plan.

The decision that follows: both device databases are watched as opaque blobs
(modification time, byte size, SHA-1), which is enough to prove whether a
re-export or a sync touched them, while the substantive questions are answered
from the ANLZ layer, the `Contents/` file tree, and direct observation in
rekordbox and on the player. If a specific finding later hinges on a device
track-table row, building an `export.pdb` kaitai reader is the first escalation;
the encrypted store is the last resort.

## Fixtures

Four tracks from the `export test` playlist, chosen so that three convert cases
and one control are covered, and so cue-bearing tracks carry the cue-survival
measurement. Convert outputs 16-bit / 44.1 kHz, so the source resolution sets
which case each track exercises.

| Fixture | ContentID | Song | Source | Cues | Round 1 conversion | Role |
| --- | --- | --- | --- | --- | --- | --- |
| T1 container-only | 53013048 | End It | FLAC 16/44.1 | 4 | to AIFF 16/44.1 (bit-identical) | Path and extension change, zero sample change |
| T2 lossy | 121715696 | 365 featuring shygirl | FLAC 16/44.1 | 1 | to MP3 320 | Lossy target, largest file-size shrink |
| T3 sample-changing | 54793376 | Charli xcx - Spring breakers (hazboy rem) | AIFF 24/44.1 | 4 | to WAV 16/44.1 (requantize) | Bit-depth reduction, the isolation case |
| T4 control | 258421826 | На такси | FLAC 16/44.1 | 1 | none | Proves export and sync work absent convert |

T1 and T3 carry four cues each, so cue survival is measured on both a
sample-preserving and a sample-changing conversion. The playlist holds no 24/48
source, so a pure sample-rate downsample is not available here; the 24-bit AIFF
supplies the bit-depth-only case, which the desktop drift study showed triggers
the full grid shift on its own. The maintainer confirms or swaps any fixture
before the first run.

## Snapshot Tooling

One read-only script, `scripts/export_snapshot.py <stage>`, captures the
whole drive state in one pass and writes `evidence/export-<stage>.json`:

- **`Contents/` tree:** every audio file's device-relative path, extension, byte
  size, mtime, and SHA-1. This is what detects a duplicated file, an orphaned
  old-extension file, or an in-place replacement.
- **`USBANLZ/` per track:** the ANLZ set's UUID folder, the parsed `PPTH`, the
  cue-list counts and positions, the `PQTZ` grid (count, BPM, first and last
  beat), and a SHA-1 per waveform tag. This is the device cue and analysis truth.
- **Device databases as blobs:** `export.pdb`, `exportExt.pdb`, and
  `exportLibrary.db` (plus WAL and SHM) recorded by mtime, size, and SHA-1 only.

The desktop side reuses `../shared/scripts/subject_snapshot.py <content_id> <stage>`
against `master.db`, so each round pairs a desktop snapshot with a drive snapshot
at every stage. A companion `export_diff.py <stageA> <stageB>` prints the deltas:
files added, removed, or changed; ANLZ cue and path changes; and which device
blobs moved.

The script is the one piece of new code. It builds on the existing snapshot
approach and writes only to `evidence/`, never to the drive or the database.

## Round 1: Re-Export After Convert

Stages, each snapshotted on both the drive and `master.db`:

1. **`r1-00-baseline`.** The drive as it stands, right after the backup. Record
   each fixture's exported file, ANLZ cue counts, `PPTH`, and the device-blob
   hashes.
2. **`r1-10-postconvert`.** Convert T1, T2, and T3 in the desktop library through
   the CLI, dry-run first, then real. Snapshot `master.db` and confirm the
   expected row changes (`FileType`, path columns, `SampleRate`/`BitDepth` where
   they move) and the known stale `FileSize`. The drive is untouched at this
   stage, so its snapshot must be byte-identical to baseline; confirm it.
3. **`r1-20-postexport`.** Re-export the `export test` playlist to `D:` through
   the normal rekordbox export, quit rekordbox, and snapshot the drive.

The `r1-10` to `r1-20` drive diff is the result. What to read from it:

- **Duplicate versus replace.** For each converted fixture, does `Contents/` now
  hold the new-extension file alone (in-place replace), the new file beside the
  stale old-extension file (orphan), or a second copy under a suffixed name
  (duplicate)? The control T4 must be unchanged.
- **Change detection.** Did rekordbox export anything at all for the converted
  tracks, or did it judge the export current and skip them? The stale desktop
  `FileSize` is a plausible confounder, since a size-based freshness check would
  read the wrong size; the ANLZ and file hashes reveal whether a copy actually
  happened.
- **ANLZ refresh.** For a re-exported track, does the device ANLZ carry a `PPTH`
  with the new extension and a re-populated cue list, or does the old ANLZ
  persist against a new-extension audio file?
- **Device DB movement.** Did `export.pdb` and `exportLibrary.db` change, which
  would indicate the device track table re-pointed to the new format?

Hypothesis: rekordbox keys the export on the collection track identity, not the
file bytes, so it re-copies the converted file and refreshes the ANLZ, with the
main risk being a leftover orphan of the old-extension file in `Contents/`.

## Round 2: Sync-Back After Convert

This round starts from a clean baseline export.

**Hardware adjustment.** The maintainer's CDJ does not play
FLAC and writes memory cues only (not hot cues). The original playlist was FLAC,
so the fixtures were first converted to AIFF (a CDJ-playable lossless format) and
re-exported to a freshly wiped drive, making that AIFF export the Round 2
baseline. The conversion whose sync-back impact is under test therefore becomes a
*second* conversion, applied after the device edits: T1 AIFF->WAV, T2 AIFF->MP3,
T3 AIFF->WAV. The device edit is a memory cue rather than a hot cue. The four
fixtures still form a clean matrix: T1 and T2 are edited and reconverted, T3 is
reconverted but not edited, T4 is edited but left AIFF (control).

Stages (labelled `r2b-*` to distinguish them from the pre-adjustment design):

1. **`r2b-00-baseline`.** Fixtures converted FLAC->AIFF in the library, drive
   wiped, playlist re-exported fresh. All four fixtures are AIFF on the device.
   Snapshot the drive and the four `master.db` rows.
2. **`r2b-10-deviceedit`.** On the CDJ, add one memory cue to T1, T2, and the
   control T4, and play each far enough to register a play, so both a cue write
   and a play-count or history change exist on the device. Leave T3 untouched.
   Snapshot the drive; the device databases and the edited tracks' ANLZ should
   differ from baseline, confirming the player wrote the changes.
3. **`r2b-20-postconvert`.** In the library, convert T1->WAV, T2->MP3, T3->WAV.
   Snapshot `master.db`. The collection files the export came from now have new
   extensions, paths, and formats, while the drive still holds the AIFF copies
   plus the fresh device edits.
4. **`r2b-30-postsync`.** Bring the drive back and run the normal sync of device
   changes into the collection. Quit rekordbox and snapshot `master.db` and its
   `DjmdCue` rows for all four fixtures.

The `r2-20` to `r2-30` desktop diff is the result. What to read from it:

- **Match survival.** Did the device edit reach the correct collection track?
  rekordbox links a device track to a collection track by an internal identity,
  not by path, so the link should survive a convert that changed only the path
  and format; this is the hypothesis to break. Compare the synced cue and play
  count against the converted T1 and T2 rows.
- **Cue merge.** Does the new hot cue appear on the converted track's `DjmdCue`
  set at the position the player wrote, and are the pre-existing cues intact?
- **Play-count and history landing.** Did the play count, `DJPlayCount`, or the
  history entry attach to the converted track?
- **Duplication or drop.** If the match failed, did the sync create a second
  collection row for the device track, or silently drop the edit? The control T4,
  edited but never converted, must sync cleanly and is the reference for a
  successful match.
- **Convert-versus-sync interaction on the file itself.** Confirm the sync does
  not attempt to reconcile the drive's old-extension audio against the new
  desktop file in a way that corrupts either.

Hypothesis: the internal linkage survives, so the cue and play count merge onto
the converted track correctly; the failure mode to watch is a path-based match
that misses and either drops the edit or duplicates the row.

## Round 3: Sync-Back on a Device Library Plus Device

Round 2 used a player that writes cues to the legacy `export.pdb`. Round 3 repeats
the sync-back on a Device Library Plus player, which writes to the encrypted
`exportLibrary.db`, to see whether that path is also broken by convert. The
`exportLibrary.db` SQLCipher key is now known (a static, machine-independent
constant, `cipher_compatibility=4`), so `export_snapshot.py` reads the device
`content`, `cue`, and `history` tables directly; the device side is instrumented,
not blob-watched.

The device stores a convert-stable link, `content.masterContentId`, equal to the
desktop `DjmdContent.ID`. Round 2 showed that the legacy `export.pdb` also carries
that ID yet the sync-back still dropped the converted tracks' edits, so a stable
ID alone does not predict survival. The open question is whether the Device
Library Plus sync-back honors `masterContentId` (survives convert) or applies the
same file-identity gate the PDB path did (drops the edit).

Fixtures are three pristine FLAC tracks the earlier rounds never touched
(R3-A Hackney Parrot `268012584`, R3-B I Felt Love `11317782`, R3-C Habla Tu
Verdad `140193439`), so no restore is needed and the desktop ANLZ stay
consistent. The device plays FLAC, so no AIFF pre-baseline is required.

Stages (`r3-*`):

1. **`r3-00-baseline`.** Drive wiped, playlist re-exported fresh; all three
   fixtures FLAC on the device. Snapshot the drive (including decrypted DB-Plus)
   and the three `master.db` rows.
2. **`r3-10-deviceedit`.** On the Device Library Plus player, add one cue and a
   play to R3-A, R3-B, and the control R3-C. Snapshot; the DB-Plus `cue` and
   `content.djPlayCount` should now show the edits directly.
3. **`r3-20-postconvert`.** Convert R3-A->AIFF and R3-B->MP3 in the library; R3-C
   stays FLAC. Snapshot `master.db`.
4. **`r3-30-postsync`.** Sync device changes back into the collection. Snapshot
   `master.db` and `DjmdCue`, and diff against the DB-Plus device state. The
   result: does the DB-Plus edit reach the converted collection track (R3-A, R3-B)
   or only the unconverted control (R3-C), as the PDB path did.

## Revert and Backup Protocol

Both rounds write to real stores, so the backup precedes everything and covers
both the drive and the desktop.

Before Round 1:

1. Back up `master.db` to the existing backup root `A:/rb-convert-test-backup/`.
2. Back up the entire `D:/PIONEER/rekordbox/` directory (all device databases
   plus WAL and SHM) and record a manifest (path, size, SHA-1) of `D:/Contents/`
   and `D:/PIONEER/USBANLZ/`. Backing up the whole `PIONEER` tree is the safe
   move if space allows.

Convert keeps the original audio unless `--delete-originals` is set, so sources
need no special handling; leave originals in place for both rounds.

Between rounds: restore `master.db` and the full `D:/PIONEER/rekordbox/`
directory from the backup, delete any converted output files created in Round 1,
and delete any new-extension or orphaned files the re-export wrote to
`D:/Contents/`. Round 2 must begin from the exact baseline export, verified by
re-running `export_snapshot.py r2-00-baseline` and diffing it against
`r1-00-baseline`.

## What Each Run Answers

| Question | Round · stage diff | Measurement | Hypothesis |
| --- | --- | --- | --- |
| Duplicate, replace, or orphan on re-export | 1 · `r1-10`→`r1-20` | `Contents/` file set per fixture: new file alone, new plus stale, or suffixed duplicate | In-place replace, with a possible orphan of the old-extension file |
| Does re-export detect the change | 1 · `r1-10`→`r1-20` | Whether any copy or ANLZ write happened for converted tracks | Detected by track identity; stale `FileSize` does not suppress it |
| Device ANLZ refresh | 1 · `r1-10`→`r1-20` | New-extension `PPTH` and re-populated cue list in the device ANLZ | Refreshed on re-export |
| Sync-back match survival | 2 · `r2-20`→`r2-30` | Synced cue and play count land on the converted collection row | Internal linkage survives the format change |
| Cue and play-count merge | 2 · `r2-20`→`r2-30` | New hot cue at the player-written position; play count or history attached; prior cues intact | Clean merge onto the converted track |
| Duplication or drop on mismatch | 2 · `r2-20`→`r2-30` | A second collection row, or a missing edit, versus the clean control | No duplication; control T4 syncs cleanly |

## Open Risks and Notes

- The encrypted `exportLibrary.db` stays a blob, so a change that lives only in
  Device Library Plus and never reaches the ANLZ or the legacy PDB is visible
  only as "the blob moved," not in detail. If a Round 2 result appears to hinge
  on Device Library Plus content, that is the trigger to reconsider the key work.
- Player behavior varies by firmware and by whether the drive is used in
  `rekordbox` device mode versus Device Library Plus. Record the unit model and
  firmware alongside the `r2-10` snapshot so the sync path is reproducible.
- The desktop findings apply unchanged underneath: convert does not move cues or
  the grid on the desktop, so any cue or grid change observed here originates in
  the export or the sync, not in convert.
- Single trials per fixture, as with the earlier in-app work. The goal is to
  characterize the behavior and its failure modes, not to establish a rate.
