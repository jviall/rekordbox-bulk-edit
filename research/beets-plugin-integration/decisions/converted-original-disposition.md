# What Happens to the Original When the Plugin Converts

**Status:** settled 2026-09-07 by the maintainer, before any plugin code exists.
Closes the open question raised in `../beets-plugin-integration.md`.

## Context

`rbe convert` transcodes a file beside its source and repoints the existing
`DjmdContent` row at the output. The row is repointed unconditionally; whether
the source file is deleted is a separate decision, taken by
`--delete-originals`, whose default is `none`: the original is kept unless the
user asks for it to go.

That default is what leaves the two libraries unable to agree, and under `none`
it does so on every conversion rather than occasionally. Rekordbox forgets the
original in every mode, so when the file survives, a beets library that records
both files holds two beets items where rekordbox holds one `DjmdContent` row, and
only one of the two items corresponds to a row. See
[rbe convert Repoints the Row, and the Original File May Outlive
It](../beets-plugin-integration.md#rbe-convert-repoints-the-row-and-the-original-file-may-outlive-it).

Deleting originals (`all`) was considered as the plugin default, on the grounds
that converting during a beets import means replacing the track's source rather
than adding a rendition of it, and that only deletion produces a state both
libraries can represent. It was rejected. `all` deletes the original whether or
not the conversion lost anything, so a 96 kHz 24-bit source going to the 44.1 kHz
16-bit target, or to MP3, would have its only high-resolution copy destroyed
during a bulk import, with the loss discovered late. Diverging from the wrapped
command in the destructive direction is also the wrong way for a default to
surprise someone.

## Decision

**The plugin inherits `--delete-originals: none`.** It does not diverge from the
command it wraps. `all` and `lossless` are exposed as plugin configuration for
users who want them.

**The plugin records the output as the beets item that rekordbox knows about, and
leaves any surviving original as a beets item of its own.** Concretely:

| Original | Beets action | Result |
| --- | --- | --- |
| kept (`none`, the default) | register the output as a new item, leave the existing one alone | 2 items, 1 row; the new item is the one with a row |
| deleted (`all`, or `lossless` on a lossless conversion) | repoint the existing item at the output | 1 item, 1 `DjmdContent` row, agreeing |

Repointing when the original survives is the option not taken. It would leave the
source file on disk and named by neither database — managed by nothing, which is
worse than a duplicate row.

## Consequences

**Registering is the default path; repointing serves the opt-in modes.** Under
`none` every conversion keeps its original, so the plugin registers and never
repoints unless the user has chosen `all` or `lossless`. Under `lossless` it does
both in the same run, since fidelity is decided per file. Both paths have to
exist; only one is on the default route.

**The repoint keeps the beets item id**, because `item.path = out; item.read();
item.store()` is an update rather than a reimport. Anything the user has keyed on
that id survives a conversion.

**The register needs `album_id` set by hand.** `Library.add` does not attach the
new item to an album; beets does that in the import pipeline, which the plugin is
not running. Left unset, the transcode will not appear under `beet ls -a` and will
not inherit album art or album-level flexible attributes.

**A beets library grows past the rekordbox one by default, by design.** Every
kept original is an item with no `DjmdContent` row, and under `none` that is every
conversion. It is the honest record of what is on disk, but it makes "beets item
without a rekordbox row" the normal state rather than an anomaly, and a
reconciliation must not treat it as an error to repair.

## Open

- Whether a kept original's beets item should carry a marker distinguishing it
  from an item that has simply never been sent to rekordbox, so a reconciliation
  can tell a deliberate leftover from a genuine gap.
