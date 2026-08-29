# Commit Semantics: session.commit Against db.commit, and the USN Gap

**Status:** open. Recorded while designing `import`; deliberately not addressed there.

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

## Consequences Today

Every row that `edit`, `convert`, and `import` write carries no `rb_local_usn`, and
the global counter does not advance. **The practical effect is untested.** The
plausible risk is that cloud or device synchronization cannot tell the row
changed, but this has not been verified, and the claim should not be repeated as
though it had been.

`add_to_playlist` is unaffected by the XML gap: it appends a `DjmdSongPlaylist`
row and never touches `playlist_xml`. It does not, however, update the parent
playlist's `updated_at`, so a playlist whose membership changes keeps a stale
timestamp in both the database and the XML. That is upstream behavior, not
something this repository introduces.

## Decision

`import` commits through `db.session.commit()`, consistent with `edit` and
`convert`, and does not create playlists. Requiring `--playlist` to name an
existing playlist keeps the command clear of `masterPlaylists6.xml` entirely,
so the XML gap cannot be reached by any `import` code path.

The USN gap is left as it stands. It predates `import`, spans all three write
commands, and closing it for one command alone would introduce an inconsistency
worse than the gap.

## What a Future Fix Has To Reconcile

Anyone addressing this should treat it as one cross-cutting change across all
write commands rather than a per-command fix:

1. **Test the consequence first.** Determine what actually breaks when a row
   carries no USN, before designing around an assumed failure.
2. **Preserve the running-rekordbox prompt.** A shared commit helper needs the
   USN and XML handling from `db.commit()` without its unconditional
   `RuntimeError`, since that would remove an affordance users rely on.
3. **Handle the XML whenever playlists are created or deleted.** Any future
   playlist creation, in `import --to-playlist` or elsewhere, must save
   `masterPlaylists6.xml` or leave rekordbox in the state it warns about.
4. **Decide on `updated_at` propagation** for playlists whose membership changes.
