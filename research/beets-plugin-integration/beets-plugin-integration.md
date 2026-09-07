# Integrating rekordbox-edit With Beets

## Question

Beets manages a music library: it tags files, relocates them under a path
template, and records the result in a SQLite database. Rekordbox maintains its
own database of the same files, keyed by path. When beets moves or transcodes a
file, the rekordbox row pointing at it becomes wrong.

What integration does beets' plugin architecture actually permit, and what shape
should a rekordbox-edit plugin take? Three workflows frame the question:

1. **Convert, then follow.** A user runs `rbe convert` over tracks rekordbox
   manages. Each file is transcoded beside its source and its rekordbox row is
   repointed at the output; depending on the mode, the source is then deleted or
   kept. Beets manages the same files and still points at the sources. The new
   paths have to reach the beets library, and where the source is kept the two
   databases end up disagreeing about how many tracks exist.
2. **Repoint after a move.** A user imports files that beets relocates, and
   wants the rekordbox rows to follow, along with any columns beets can now
   populate better than the original tags did.
3. **Reimport and update.** A user re-runs the autotagger over items already in
   both databases and wants the improved metadata propagated to rekordbox.

## Terminology

Both tools have a library, a convert, and an import, and this document discusses
all six. Two conventions keep them apart.

**A "row" without qualification is a `DjmdContent` row**, in rekordbox's
database. Beets' rows are never called rows: they are *items* and *albums*.

**A bare command name is beets'.** `import`, `convert`, and `modify` mean
`beet import`, the beets convert plugin, and `beet modify`. rekordbox-edit's are
always written `rbe convert`, `rbe edit`, `rbe import`, or named by the API
function behind them (`convert()`, `edit()`, `import_tracks()`).

### Beets

| Term | Meaning |
| --- | --- |
| **item** | One row of beets' SQLite library, describing one audio file: its path plus the fields read from its tags. |
| **album** | A row grouping items. An item's `album_id` names one; `Library.add` leaves it unset. |
| **singleton** | An item deliberately attached to no album. `beet import -s`, or `import.singletons: yes`. |
| **library directory** | The root beets relocates files under, the `directory:` config key. |
| **path template**, path format | The `paths:` config deciding where under the library directory a file belongs, such as `$albumartist/$album/$track $title`. `Item.destination()` evaluates it. The extension is not part of it; it comes from the file the item currently names. |
| **flexible attribute**, flexattr | A field held only in beets' database and never in the file's tags. Any field name beets does not recognise becomes one. |
| **media field** | A field bound to a real tag frame in the file, so `item.write()` stores it and `item.read()` recovers it. Plugins may declare new ones. |
| **the import pipeline** | The staged process `beet import` runs: task construction, tagging, plugin stages, then file relocation. Order matters throughout this document. |
| **import stage** | A plugin callback running *inside* that pipeline, given the session and the task, able to change what happens next. |
| **event**, listener | A named notification beets sends. A listener is told what happened; with a single exception it cannot alter the outcome. |
| **autotag** | Beets matching a file's metadata against MusicBrainz. On by default. |
| **as-is import**, `-A`, `autotag: no` | Importing with that lookup switched off, so beets keeps the file's existing tags. Internally the task's choice becomes `Action.ASIS` rather than `Action.APPLY`, which is what suppresses three events and tag writing. This document says **as-is import** for all three spellings. |
| **apply** | The opposite state, `Action.APPLY`: matched metadata is being written onto the item. `task.apply` is true only here. |
| **reimport** | Re-running the importer over files already in the library, `beet import -L`. It removes the existing items and inserts new ones rather than updating in place. |
| **the convert plugin** | Beets' bundled transcoder, `beetsplug/convert.py`. Never `rbe convert`. |
| **`convert.auto`**, `auto_keep`, `--keep-new` | Its modes, which differ in where the output lands and whether the library entry follows it. Tabulated under [Going Through the Beets Convert Plugin Is the Other Direction](#going-through-the-beets-convert-plugin-is-the-other-direction). |

### Rekordbox-edit

| Term | Meaning |
| --- | --- |
| **`DjmdContent`** | Rekordbox's track table, one row per track. `FolderPath` and `FileNameL` hold the location, `FileType` a numeric format code. |
| **`rbe convert`** | rekordbox-edit's transcode command. Encodes beside the source and repoints the existing `DjmdContent` row at the output. |
| **`rbe edit`** | Its field-editing command. Writes named columns onto matched rows through per-field handlers. |
| **`rbe import`**, `import_tracks()` | Its command for creating `DjmdContent` rows for files rekordbox does not yet know about, matched by resolved case-folded path. |
| **field handler** | The per-column unit `rbe edit` is built from, owning one field's validation and write. |
| **`--delete-originals`** | `rbe convert`'s policy for the source file once the output exists. The default `none` keeps it; `all` always deletes it; `lossless` deletes it only when the conversion lost no audio information. |
| **USN** | Rekordbox's change counter, global in `agentRegistry.localUpdateCount` and per-row in `rb_local_usn`. Every row rekordbox-edit writes is stamped. |
| **ANLZ** | Rekordbox's on-disk analysis files for a track, which embed the track's path and so must be rewritten when it moves. |

## Method

Code reading against beets 2.5.1 on Python 3.13.15, and rekordbox-edit at
`d920d9b`. Five probes under `scripts/` produce the files under `evidence/`:

- `event_probe.py` installs a plugin listening to every event in
  `beets.plugins.EventType` plus the convert plugin's `after_convert`, then runs
  an import and a reimport against a throwaway library.
- `id_stability.py` records item identifiers before and after a reimport, using
  the unchanged file paths as a control.
- `media_field_roundtrip.py` stamps a plugin-declared media field and reads the
  value back out of the file with mediafile alone.
- `convert_repoint.py` imports fixtures into a throwaway library, transcodes each
  one beside its source the way `rbe convert` does, and reports what it costs to
  repoint the existing item at the output or to register the output as a new one.
- `file_level_encode.py` builds rekordbox-edit's `_EncodeJob` by hand from a path
  on disk and runs `_encode_one` against it, with and without a declared
  rekordbox file type. It runs in the rekordbox-edit environment rather than
  beets'; the rest run against `beet` on `PATH`.

Each builds its own library or output directory in a temp directory, and none
needs the network. The audio fixtures are `tests/e2e/fixtures/audio/`.

## Findings

### The Plugin Surface

A plugin subclasses `BeetsPlugin` and extends beets through seven mechanisms,
all in `beets/plugins.py`:

| Mechanism | Entry point | Purpose |
| --- | --- | --- |
| Subcommands | `commands()` (line 270) | Add `beet <verb>` |
| Event listeners | `register_listener()` (line 355) | React to a named event |
| Import stages | `early_import_stages`, `import_stages` (lines 286, 296) | Run inside the import pipeline |
| Media fields | `add_media_field()` (line 339) | Bind a field to real tag frames |
| Flexible types | `item_types`, `album_types` attributes (line 516) | Typed database-only fields |
| Queries | `queries()` (line 335), `item_queries` | New query prefixes |
| Template fields | `template_field()` (line 379) | New `$name` in path formats |

Events are declared as a `Literal` of 29 names (line 70). `send()` returns the
non-None values handlers produced (line 636), but only one caller consumes them:
`handle_created` treats the return of `import_task_created` as replacement tasks
(`importer/tasks.py:345-357`). Every other event is notification only. A
listener cannot veto, defer, or alter what beets is about to do.

Import stages are the mechanism that can. They receive the session and the task
and run inside the pipeline rather than beside it.

### The Import Pipeline Inserts Items Before It Moves Files

The pipeline is assembled in `importer/session.py:195-228`. Plugin stages are
appended after the tagging stages and before `manipulate_files`. Because
`_apply_choice` calls `task.add(session.lib)` (`importer/stages.py:323`) during
the tagging stage, items reach beets' database well before their files are
relocated.

The observed order for an album import with `convert.auto_keep` enabled
(`evidence/event-order.txt`):

| Phase | Events |
| --- | --- |
| Startup | `pluginload`, `library_opened`, `import_begin` |
| Task construction | `import_task_created` |
| Item insertion | `database_change` per album and item |
| Plugin stages | convert runs here: `write`, `after_write`, `after_convert` |
| File relocation | `item_copied` per item, then `database_change` |
| Finalisation | `import_task_files`, `album_imported`, `import`, `cli_exit` |

Two consequences follow. An import stage observes items already in the database
at their pre-move paths, so a stage that reads `item.path` reads a path that is
about to become wrong. And `after_convert` fires **before** `item_copied`, so a
listener pairing the convert output with `item.path` pairs it with the source
location rather than the library destination.

### The Autotagger Gates Three Events, None of Them Load-Bearing

Under `autotag: no`, beets substitutes `import_asis` for the candidate lookup and
user query stages (`importer/stages.py:219-231`). Three events therefore never
fire: `import_task_start` and `import_task_choice`, which those stages send, and
`import_task_apply`, which `_apply_choice` sends only when `task.apply` is true.
That property is `choice_flag == Action.APPLY` (`importer/tasks.py:218`), and an
as-is import sets `Action.ASIS`. The probe confirms all three absent.

All three report on the tagging decision, which a rekordbox integration does not
need. Everything it does need survives, for both task types:

| Signal | Album, `-A` | Singleton, `-A` |
| --- | --- | --- |
| `item_copied`, with source and destination | fires | fires |
| Completion | `album_imported` | `item_imported` |
| `import_task_files`, `cli_exit` | fire | fire |

An as-is import is therefore fully observable. This matters because it is the
mode a derived or downstream library runs in, and the mode in which nothing
should be re-queried from a metadata source.

Tag writing is suppressed by the same flag. `manipulate_files` calls
`item.try_write()` only when `write and (self.apply or self.choice_flag ==
Action.RETAG)` (`importer/tasks.py:482`), so an as-is import leaves file tags
untouched even with `write: yes`. That is coherent rather than limiting: beets
has produced no new tag data, so there is nothing to write. It also costs a
rekordbox integration nothing, because `import_tracks` reads tags from the file
rather than from beets.

The gap that does exist is on the other side. `edit` never reads tags;
`FolderPathField` probes only audio properties (codec, duration, sample rate,
size). Populating other rekordbox columns from beets metadata has no path
through the current handler set.

### item_imported Fires for Singletons Only

`album_imported` is sent from the album task's `_emit_imported`
(`importer/tasks.py:343`); `item_imported` is sent from the singleton task's
(line 684). An album import emits no per-item completion event. A plugin needing
per-item notification on both paths must register for both and iterate
`album.items()` in the album case.

### Relocation Events Carry Source and Destination

`item_moved`, `item_copied`, `item_linked`, `item_hardlinked`, and
`item_reflinked` are sent from `Item.move()` with `item`, `source`, and
`destination` (`library/models.py:1033-1065`). These are the only events pairing
both paths, which makes them the natural repoint trigger: locate the rekordbox
row whose path equals `source`, rewrite it to `destination`.

Three cautions apply. The event fires per operation, so the mode determines which
name to listen for and a plugin should register all five. With `copy: no` and
`move: no`, none fires. And on a reimport of in-library files, `source` and
`destination` are equal (`evidence/event-order.txt`, events 25 to 30), so a
handler must compare them before writing anything.

### Beets Item Identifiers Do Not Survive a Reimport

A reimport removes the existing items and inserts new ones. `add` calls
`record_replaced` then `remove_replaced`, which calls `dup_item.remove()` per
replaced item (`importer/tasks.py:612-624`), emitting `item_removed` and
`album_removed`. Measured across three files whose paths did not change
(`evidence/id-stability.txt`):

| File | ID before | ID after |
| --- | --- | --- |
| Wave Alpha.flac | 1 | 4 |
| Wave Beta.flac | 2 | 5 |
| High Quality.mp3 | 3 | 6 |

Every identifier changed while every path was preserved. **No mapping between
the two databases may be keyed on the beets item identifier.** The durable keys
are the file path, which is what rekordbox itself matches on, and a value stamped
into the file.

Reimports preserve flexible attributes, with an exception list. `reimport_metadata`
copies the replaced item's `_values_flex` onto the new item, minus the fields in
`REIMPORT_FRESH_FIELDS_ITEM` (`importer/tasks.py:54-62`). A database-only
identifier therefore survives a reimport, provided the plugin does not add its
field to that list.

### A Plugin-Declared Media Field Round-Trips in the File

`add_media_field` registers a `MediaField` on `mediafile.MediaFile` and adds the
name to `Item._media_fields`, so `item.read()` and `item.write()` carry it like
any native tag. Declaring four storage styles covers the containers rekordbox
accepts. Stamped through `beet modify` and read back with mediafile alone, with
no beets database involved (`evidence/media-field-roundtrip.txt`):

| Container | Carrier | Result |
| --- | --- | --- |
| FLAC | Vorbis comment | round-trips |
| AIFF | ID3 chunk | round-trips |
| WAV | ID3 chunk | round-trips |
| MP3 (CBR and VBR) | TXXX | round-trips |

This is the mechanism for a durable join that survives operations beets does not
observe, at the cost of writing tags.

### rbe convert Repoints the Row, and the Original File May Outlive It

`_apply_converted_record` (`api/_convert.py:182`) writes the output's file name,
folder, and audio columns onto the **existing** `DjmdContent` row. Nothing in
`convert()` inserts a row. The rekordbox identifier is therefore stable across a
conversion, and rekordbox never holds the source and the output at the same time.

Whether the source file survives is a separate decision. `_deletes_original`
(`api/_convert.py:471`) consults `--delete-originals`, whose default is `none`:
the original is kept unless the user asks otherwise. `all` always removes it, and
`lossless` removes it only when the conversion lost no audio information —
`_classify_fidelity` counts an unknown bit depth and any down-sample as lossy, and
MP3 output is never lossless, so under `lossless` a hi-res source is kept and a
44.1 kHz 16-bit source is not.

| `--delete-originals` | Source file | `DjmdContent` rows | Beets items, if nothing is done |
| --- | --- | --- | --- |
| `none` (default) | kept | 1, at the output | 1, at the source; output unknown |
| `all` | deleted | 1, at the output | 1, at a path that no longer exists |
| `lossless`, lossless conversion | deleted | 1, at the output | 1, dangling |
| `lossless`, lossy conversion | kept | 1, at the output | 1, at the source; output unknown |

Rekordbox forgets the original in every row of that table. Beets can keep it. The
two libraries therefore agree only when the original is deleted; when it is kept,
a beets library that records both files holds two items where rekordbox holds one,
and only one of the two corresponds to a rekordbox row. Under the default that is
not the edge case but the ordinary outcome, so what the plugin does about it is a
policy question it has to answer up front rather than a corner to handle later. It
is answered in [What Happens to the Original When the Plugin
Converts](decisions/converted-original-disposition.md): the plugin keeps the
`none` default and records the output as the item rekordbox knows about, leaving
the original as a beets item with no `DjmdContent` row.

### The Converted File Already Sits Where Beets Wants It

`_get_output_path` (`api/_convert.py:389`) writes the output into the source's
directory, keeping the stem and swapping the extension. `Item.destination` builds
every path segment from the path template but takes the extension from
`self.filepath.suffix` (`library/models.py:1227`), so an item pointing at the
output resolves to the templated path carrying the new extension.

Under a template that does not mention anything the conversion changes, those are
the same path (`evidence/convert-repoint.txt`):

| Import, template | `rbe convert` output | `item.destination()` | Same |
| --- | --- | --- | --- |
| singletons, `$artist/$title` | `Alpha/Wave Alpha.aiff` | `Alpha/Wave Alpha.aiff` | yes |
| album, `$artist/$title` | `Compilations/Lossless Vol 1/00 Wave Alpha.aiff` | the same | yes |
| either, `$artist/$format/$title` | as above | `Alpha/FLAC/Wave Alpha.aiff` | no |

In the common case the plugin has no file to move: recording the new path in both
databases is the whole job. A library whose template keys on `$format`,
`$bitrate`, or `$samplerate` is the exception, and it fails in two ways at once.
The destination genuinely differs, so the file has to be moved after the fact —
which changes the path a second time, after `rbe convert` has already committed
the rekordbox row, leaving that row pointing at a file that is gone until the move
is pushed back.

And the `FLAC` segment above is the pre-conversion value: `destination()` reads
`format` from the beets item, not from the file that item now names. A plugin
must re-read the item before its destination means anything.

### Repointing an Item Refreshes the Audio Fields and Discards Database-Only Ones

Beets' own way of pointing an item at a transcode is
`item.path = converted; item.read(); item.store()`, which is what the convert
plugin does under `--keep-new` (`beetsplug/convert.py:457-459`). Measured against
a FLAC repointed at its AIFF conversion (`evidence/convert-repoint.txt`):

| | Before | After |
| --- | --- | --- |
| `id` | 1 | 1 |
| `format` | FLAC | AIFF |
| `bitrate` | 96592 | 705600 |
| `samplerate` | 44100 | 44100 |
| a flexible attribute | set | preserved |
| `comments`, set in the database only | `'db-only edit...'` | `''` |

The identifier survives, so a repoint is not a reimport and nothing keyed on the
item id breaks. Flexible attributes survive, because `read()` assigns only media
fields. Fixed fields do not: `read()` overwrites every media field from the
output's tags. Under `write: yes` beets has already written its metadata to the
source and ffmpeg's `map_metadata 0` carries those tags into the output, so in
the ordinary case the file agrees with the database and nothing is lost. A value
that reached the database without reaching the file is lost.

### A Registered Transcode Has No Album

Where the original is kept, the output has to be registered rather than
substituted. `Item.from_path` followed by `Library.add` does that: the probe's
output lands as id 3 with the correct format and bitrate, while the original
keeps id 2 and stays in the library (`evidence/convert-repoint.txt`).

Its `album_id` is `None`, including in the album import where the original's is
`1`. Beets attaches items to albums in the import pipeline, not in `add`, so a
plugin registering a transcode outside the pipeline must set `album_id` itself or
the new item will not appear under `beet ls -a`, will not inherit album art, and
will not see album-level flexible attributes.

### Going Through the Beets Convert Plugin Is the Other Direction

The remaining option for workflow 1 is to let beets do the transcoding and have
the plugin follow it. That inverts which tool owns the conversion, and it is worth
recording why it is the weaker of the two.

The convert plugin sends `after_convert` with `item`, `dest`, and `keepnew`
(`beetsplug/convert.py:477-483`). That name is absent from the `EventType`
literal, so it is a plugin-to-plugin convention rather than part of beets' typed
event surface, and it carries no compatibility guarantee.

Convert's three modes differ in what they leave behind:

| Mode | Output location | Library entry |
| --- | --- | --- |
| `beet convert -d DEST` | under `DEST` | unchanged, still the source |
| `convert.auto` | temp file, then the library path | repointed at the transcode |
| `convert.auto_keep` | `convert.dest` | unchanged, still the source |
| `beet convert --keep-new` | original moved to `-d`, transcode at the item path | repointed at the transcode |

Only the modes that repoint an existing entry put the output in the database, and
they do so by replacing the source entry rather than adding an item. No mode
registers the transcode as a new item. Nothing in beets records that the source
and the output are related.

Following that from a plugin means depending on `after_convert`, an event outside
`EventType`, and working around its firing before the item has moved. It also
gives the plugin less than driving `rbe convert` does: in the modes that repoint,
the source entry is replaced rather than kept, so the plugin sees the same
kept-original problem with no control over the policy, and in the modes that do
not repoint, the output is simply absent from the beets database. Neither is a
better starting point than owning the conversion.

### The Encoder Is Already Separable From Rekordbox

`rbe convert` is built around a plain dataclass rather than around a database
row. `_EncodeJob` carries a source path, file name, declared file type, output
path, temp path, and output format, and `_encode_one` is documented as
"touching no database state" (`api/_convert.py:275`). The thread pool, the
encode-to-temp-then-move, the ffmpeg argument construction, and the output probe
are all row-independent already.

Three seams hold the rekordbox coupling:

| Seam | Location | What a file-oriented caller supplies instead |
| --- | --- | --- |
| Job construction | `_encode_job_for` (line 260) | The five values directly |
| Output location | `_get_output_path` (line 389) | Its own destination, rather than the source's directory |
| Candidate selection | `_classify_convert` (line 404) | Its own list of files |

Driving it that way works today. Built by hand from a path on disk, with no
session and no row in existence, `_encode_one` encodes each fixture to the
conversion target and reports fidelity correctly (`evidence/file-level-encode.txt`):

| Source | Declared type | Result |
| --- | --- | --- |
| `01-flac-44_1k-16b.flac` | FLAC | `pcm_s16be` 44100 Hz 16-bit, lossless |
| `02-flac-96k-24b.flac` | FLAC | `pcm_s16be` 44100 Hz 16-bit, lossy (down-sampled) |
| `06-wav-96k-24b.wav` | WAV | `pcm_s16be` 44100 Hz 16-bit, lossy (down-sampled) |

One decision is semantic rather than mechanical. `_encode_one` calls
`probe_matches_file_type`, which returns `False` for a `None` file type by
design, so that "callers treat them as mismatches instead of converting blind"
(`utils.py:185`). That cross-check exists to catch a rekordbox row disagreeing
with the file it names. A caller converting a file it already holds has no second
declaration to check against, so the check is inapplicable rather than failing.
Run with `file_type=None`, every one of the three files above is skipped with
`codec_mismatch` and nothing is encoded, so the check cannot simply be left to
default. Supplying a declared type is the cheaper fix than skipping the check: the
rekordbox `FileType` code follows from the extension through
`get_file_type_for_format`, which is what the probe passes and what a beets caller
holding an `Item` can pass too.

A file-level entry point over `_EncodeJob`, with the present rekordbox-aware
`convert()` layered on it, would let a plugin transcode without a `DjmdContent`
row existing first, and would remove any dependency on the convert plugin.

### The rekordbox-edit API Carries Its Own Safety

`rekordbox_edit.api` exports `search`, `edit`, `convert`, `import_tracks`, and
`remove`. Each takes an open `Rekordbox6Database` and a request model, and each
is dry-runnable. For the three workflows, `edit` with `field="FolderPath"` repoints
a row and resynchronises the columns describing the file, and `import_tracks`
creates rows for files rekordbox does not know about, matching by resolved,
case-folded path so that repeated runs are idempotent.

Both guards a plugin would otherwise have to reproduce now live in the API.
`writing()` (`api/_utils.py:23`) raises `RekordboxRunningError` when rekordbox is
open, then holds the single-writer advisory lock for the duration of the write.
Every API write enters through it — `convert()`, `edit()`, and `import_tracks()`
each open `with writing(db, ...)` — and the CLI's own lock nests inside harmlessly.
A plugin driving the API directly therefore inherits both and must not reimplement
either.

The guard wraps only the writing region, so a dry run reaches neither check. That
is the property a plugin wants: it can plan against a library rekordbox has open,
and will be refused only when it tries to commit.

The refusal is an exception, not an exit, which shapes where a plugin puts its
write. `RekordboxRunningError` raised out of a `cli_exit` listener surfaces at the
end of an import that has already finished and cannot be replayed. That is an
argument for the subcommand below rather than against the guard.

### Rekordbox Writes Must Be Batched and Single-Threaded

Beets imports with `threaded: yes` by default, so relocation events arrive on
worker threads. Rekordbox-edit keeps every database touch on the main thread
inside `convert`, because `RekordboxAgentRegistry`'s change buffer is a class
attribute shared by every instance in the process
(`research/import-track-row-shape/decisions/commit-semantics-and-usn.md`).

A plugin must therefore not write rekordbox from an event handler. It should
accumulate the pairs it observes and flush once, from a single thread, at
`cli_exit`. Batching is also what makes the write inspectable: one transaction
that can be dry-run and re-run, rather than thousands that cannot.

## Conclusion

Beets permits the integration, and the architecture points at one shape for it.

**Collect during the import, write once at the end.** Relocation events are the
only source of paired source and destination paths, and they are notification
only, so a handler cannot usefully do more than record what it saw. A single
flush at `cli_exit` satisfies the threading constraint and produces one auditable
rekordbox transaction. The API supplies the guards, so the flush needs only to
handle being refused.

**Join on the path, never on an identifier beets controls.** Item identifiers
change on reimport while paths do not. For operations beets does not observe, a
media field carries a rekordbox identifier through any container rekordbox
accepts, at the cost of writing tags.

**Offer a subcommand alongside the listeners.** The import-time hook cannot see
anything done outside beets, and an import that has already completed cannot be
replayed if rekordbox was open at the time. A `beet rbe sync` style subcommand
that reconciles the library against rekordbox on demand covers both with the same
code, is re-runnable, and does not couple a cross-application write to an import
that has no rollback relationship with it.

Against the three framing workflows:

**Workflow 1, convert and follow**, is mechanically the easiest of the three and
semantically the hardest. `rbe convert` already writes its output where beets
wants the file, so under an ordinary path template no file moves and the plugin's
only filesystem concern is the one case where the template keys on something the
conversion changes. Both of the library-side operations are one-liners with
precedent: repointing is `item.path = out; item.read(); item.store()`, which keeps
the item id, and registering is `Item.from_path` plus `Library.add`
(`library/models.py:806`, `library/library.py:43`), which needs `album_id` set by
hand. Neither needs a second import pass and neither needs the convert plugin.

What is not mechanical is which of the two to perform, because `rbe convert`
repoints the rekordbox row unconditionally while keeping or deleting the source
file according to `--delete-originals`. Its default is `none`, so by default the
original survives — rekordbox has forgotten a file that still exists and that
beets still has an entry for, and no beets-side action reproduces the rekordbox
state: registering the output gives beets two items to rekordbox's one, and
repointing loses the surviving original from both. The deleting modes are the
opt-in case, and only there can the two libraries agree exactly.

**The plugin should not try to mirror rekordbox here**, and it should not buy
agreement by deleting more than `rbe convert` would. It keeps the `none` default
and records the output as the item rekordbox knows about — registering a new item
when the source survives, repointing the existing one when a deleting mode removed
it — treating a kept original as a beets item with no `DjmdContent` row, which is
what it now is (`decisions/converted-original-disposition.md`). A beets library
legitimately larger than the rekordbox one is therefore the normal state, and one
any reconciliation has to tolerate rather than repair.

The remaining seam is that a beets-driven conversion cannot pass `None` as the
source file type without every file being skipped, so a file-level entry point
over `_EncodeJob` must take a declared type from the caller.

**Workflow 2, repoint after a move**, is the best-supported case and needs no
custom field: `item_copied` and `item_moved` deliver both paths, and
`edit(field="FolderPath")` already resynchronises the technical columns. Its
second half is not supported. Pushing beets metadata into other rekordbox columns
needs either new field handlers or a way to pass explicit per-track values, since
`edit` reads tags from nothing and derives only audio properties from the file.

**Workflow 3, reimport and update**, is the case most likely to be got wrong,
because the reimport silently replaces items. A plugin holding beets identifiers
will appear to work and then quietly address the wrong tracks. Path-keyed
reconciliation is correct here for the same reason it is correct everywhere else.

## Open Questions

- Which rekordbox columns are worth exposing as editable beyond the current
  handler set, and which beets fields map onto them without loss.
- Whether a plugin should write tags at all. The media field is the only join
  that survives operations beets cannot see, but it modifies files that rekordbox
  may have analysed.
- What `edit` costs at library scale. It classifies every candidate, applies
  every change, and commits once, so a large reconciliation is atomic but
  unbounded in memory, and `post_commit` rewrites ANLZ files serially for every
  track whose filename changed.
- Whether the file-level encode entry point should skip the source probe's codec
  cross-check or require a declared type from the caller. Requiring one is cheap
  for a beets caller, which can derive it from the extension, and it keeps the
  guard that catches a file disagreeing with what names it.
- Whether an original that `--delete-originals: lossless` kept should carry a
  marker on its beets item, so a reconciliation can tell a deliberate leftover
  from a track that has genuinely never reached rekordbox. Raised in
  `decisions/converted-original-disposition.md`.
- Whether `rbe convert` should gain an output-directory option. It currently
  writes beside the source, which is what makes the beets destination match; a
  destination argument would break that coincidence and put the move back.
- How to sequence the second path change when the beets path template keys on
  `$format` or `$bitrate`, given that `rbe convert` commits the rekordbox row
  before beets has had a chance to move the file.
- How the plugin should behave when rekordbox is running, since the import that
  triggered it cannot be replayed.
