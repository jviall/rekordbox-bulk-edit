# Commit Semantics: session.commit Against db.commit, and the USN Gap

**Status:** settled for USNs; the `masterPlaylists6.xml` gap remains open.
Recorded while designing `import`, closed while adding USN maintenance.

## Context

Every write command in this repository commits through `db.session.commit()`.
`pyrekordbox` also offers `Rekordbox6Database.commit()`, which wraps the same
session commit in three additional behaviors. The difference was examined while
designing the `import` command, because one of those behaviors bears on playlist
creation.

## What db.commit Does That session.commit Does Not

**It refuses to run while rekordbox is open.** `db.commit()` calls
`get_rekordbox_pid()` and raises `RuntimeError` when rekordbox is running. This
repository takes a different position: `cli/_utils.py::_rekordbox_running_confirm`
warns, then offers "Continue anyway?" in interactive modes and exits only in
scripting modes. Adopting `db.commit()` would override a choice the user has
already been asked to make.

**It maintains USNs.** A USN, or unique sequence number, is rekordbox's change
counter for cloud and device synchronization. The global counter lives in
`agentRegistry.localUpdateCount`, and each touched row carries `rb_local_usn`.
`db.commit(autoinc=True)` calls
`registry.autoincrement_local_update_count(set_row_usn=True)`, which advances the
global counter once per buffered change and stamps each affected row.
`db.session.commit()` performs neither step.

Rekordbox itself maintains these. In the sampled device library, 906 imported
tracks carry sequential `rb_local_usn` values from 969 to 2694, and 2694 is
exactly that library's `localUpdateCount`. See `../import-track-row-shape.md`.

**It saves `masterPlaylists6.xml`.** `create_playlist` registers a new playlist
in that XML in memory through `playlist_xml.add(...)`, and only `db.commit()`
calls `playlist_xml.save()`. A playlist created and then committed through the
session alone exists in the database but not in the XML. `pyrekordbox` warns
about precisely this state on its next commit:

> `Playlist {ID} not found in masterPlaylists6.xml! Did you add it manually?`

## Consequences Before the Fix

Every row that `edit`, `convert`, and `import` wrote carried no `rb_local_usn`, and
the global counter did not advance. **The practical effect was untested.** The
plausible risk is that cloud or device synchronization cannot tell the row
changed, but this has not been verified, and the claim should not be repeated as
though it had been.

`add_to_playlist` is unaffected by the XML gap: it appends a `DjmdSongPlaylist`
row and never touches `playlist_xml`. It does not, however, update the parent
playlist's `updated_at`, so a playlist whose membership changes keeps a stale
timestamp in both the database and the XML. That is upstream behavior, not
something this repository introduces.

## Decision

**Status update:** the USN half is closed. See `stamp_usns` in
`rekordbox_edit/api/usn.py` and the measurements in
`../../database-concurrency/usn-maintenance.md`.

`import` commits through `db.session.commit()`, consistent with `edit` and
`convert`, and does not create playlists. Requiring `--playlist` to name an
existing playlist keeps the command clear of `masterPlaylists6.xml` entirely,
so the XML gap cannot be reached by any `import` code path.

`edit`, `convert`, and `import` now stamp every row they write and advance
`localUpdateCount` to match, in the same transaction as the rows themselves.

## How the USN Gap Was Closed

Not through `db.commit()` or `autoincrement_local_update_count`, both of which
were rejected:

- `db.commit()` refuses outright while rekordbox is running, which would remove
  the "Continue anyway?" affordance this repository deliberately offers.
- `autoincrement_local_update_count` reads the counter and writes it back.
  Measured against the real engine with two concurrent writers, that loses
  exactly one writer's increments and raises nothing. Rekordbox writes to the
  same counter, and the advisory lock has no authority over it.

Instead one expression `UPDATE ... RETURNING` reserves a block of values, so
the counter is never read into application code and cannot go stale. The
reservation lands in the transaction that writes the rows, so a crash between
them is impossible: a counter advanced past unstamped rows would hide those
rows from sync permanently.

One USN is reserved per row stamped, which does not reproduce rekordbox's
numbering. The sampled library's 906 imported tracks hold 906 distinct stamps
spread across 969 to 2694, so about 820 values in that span went elsewhere;
what consumed them was never established. Matching exactly would mean knowing
everything rekordbox counts, and it does not matter: a peer asks for rows
*above* a value, so extra values cost nothing while a reused stamp would hide
a row.

Two of the original conditions were satisfied, and one was overtaken:

1. **Test the consequence first.** Not done, and knowingly so. The maintainer
   chose to proceed on the grounds that writing rows the way rekordbox writes
   them is the standard `import` already holds itself to, and that a silent
   failure for anyone using cloud sync is worse than the cost of maintaining
   one column. The consequence of an unstamped row remains untested.
2. **Preserve the running-rekordbox prompt.** Kept. Correctness comes from the
   statement being atomic rather than from having checked for a process
   beforehand, so the prompt was never load-bearing. It no longer fires for dry
   runs, which write nothing.
3. **`RekordboxAgentRegistry` is still untouched.** Its change buffer and
   tracking flag are class attributes shared by every instance in the process,
   which is also why database work stays on the main thread in `convert`.

## What Remains Open

1. **The XML gap.** Any future playlist creation, in `import --to-playlist` or
   elsewhere, must save `masterPlaylists6.xml` or leave rekordbox in the state
   it warns about. No command creates playlists today.
2. **`updated_at` propagation** for playlists whose membership changes.
3. **The untested consequence.** Whether an unstamped row actually breaks cloud
   or device sync is still unverified. `../../convert-export-impact/` ruled out
   USNs as the cause of the one sync failure this repository has observed,
   which was a path-and-format gate, so no evidence either way exists yet.
