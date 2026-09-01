# API Reference

Everything the CLI does is available from Python. The public surface is the four functions in `rekordbox_edit.api` and the Pydantic models in `rekordbox_edit.models` that describe their inputs and outputs.

```python
from pyrekordbox import Rekordbox6Database
from rekordbox_edit.api import search
from rekordbox_edit.models import SearchRequest

db = Rekordbox6Database()
response = search(db, SearchRequest(artist=["Daft Punk"], format=["flac"]))
for track in response.tracks:
    print(track.ID, track.Title)
```

Different filter kinds — `artist` and `format` above — AND together by default; repeated values of the same filter OR together. Pass `match_all=True` to flatten everything into one AND, or `match_any=True` to flatten everything into one OR.

`--print json` on any CLI command emits exactly these response envelopes, so the models below also document the JSON you get when scripting.

## Writing Safely

`edit`, `convert`, and `import_tracks` guard their own writes. Each one refuses to run while Rekordbox is open, raising
[`RekordboxRunningError`][rekordbox_edit.errors.RekordboxRunningError], and holds a single-writer advisory lock for the
duration of the write. A `dry_run=True` call reaches neither check, because it writes nothing.

That per-call lock does not span two calls. Planning and then applying is two calls, and between them the lock is free, so
another process can change a row you are about to write. Hold the lock yourself across the pair:

```python
from rekordbox_edit.api import edit
from rekordbox_edit.locking import SCRIPTED_TIMEOUT, database_lock
from rekordbox_edit.models import EditRequest

args = EditRequest(field="Title", replace_value="Take 2", artist=["Alpha"], multi=True)

with database_lock(db.db_directory, command="edit", timeout=SCRIPTED_TIMEOUT):
    preview = edit(db, args, dry_run=True)
    # ... decide which ops to keep ...
    response = edit(db, args, ops=preview.result.edits)
```

The lock is re-entrant within a process, so the one each call takes nests inside yours at no cost. A lock held by another
process raises [`DatabaseBusyError`][rekordbox_edit.errors.DatabaseBusyError].

Without the outer lock the plan is still re-checked at apply time: an op whose row or file changed in the meantime is
reported as a `db_or_fs_changed` skip rather than applied blindly.

## Errors

Every error these functions raise on purpose descends from
[`RekordboxEditError`][rekordbox_edit.errors.RekordboxEditError], so one `except` clause covers them.
[`InputError`][rekordbox_edit.errors.InputError] also subclasses `ValueError`.

::: rekordbox_edit.errors
options:
heading_level: 3

## Functions

::: rekordbox_edit.api.search

::: rekordbox_edit.api.edit

::: rekordbox_edit.api.convert

::: rekordbox_edit.api.import_tracks

## Models

The models form three layers: the [`FilterArgs`][rekordbox_edit.models.FilterArgs] base that every command shares, the per-command requests and responses, and the lower-level domain types those req/resp models are built from.

::: rekordbox_edit.models.FilterArgs
options:
heading_level: 3

### Search

::: rekordbox_edit.models.SearchRequest
options:
heading_level: 4

::: rekordbox_edit.models.SearchResponse
options:
heading_level: 4

### Edit

::: rekordbox_edit.models.EditRequest
options:
heading_level: 4

::: rekordbox_edit.models.EditResponse
options:
heading_level: 4

::: rekordbox_edit.models.EditResult
options:
heading_level: 4

### Convert

::: rekordbox_edit.models.ConvertRequest
options:
heading_level: 4

::: rekordbox_edit.models.ConvertResponse
options:
heading_level: 4

::: rekordbox_edit.models.ConvertResult
options:
heading_level: 4

### Import

::: rekordbox_edit.models.ImportRequest
options:
heading_level: 4

::: rekordbox_edit.models.ImportResponse
options:
heading_level: 4

::: rekordbox_edit.models.ImportResult
options:
heading_level: 4

### Miscellaneous

::: rekordbox_edit.models.Track
options:
heading_level: 4

::: rekordbox_edit.models.EditOp
options:
heading_level: 4

::: rekordbox_edit.models.ConvertOp
options:
heading_level: 4

::: rekordbox_edit.models.ImportOp
options:
heading_level: 4

::: rekordbox_edit.models.SkippedTrack
options:
heading_level: 4

::: rekordbox_edit.models.SkipReason
options:
heading_level: 4
