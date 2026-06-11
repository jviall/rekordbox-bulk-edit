# API Reference

Everything the CLI does is available from Python. The public surface is the three functions in `rekordbox_edit.api` and the Pydantic models in `rekordbox_edit.models` that describe their inputs and outputs.

```python
from pyrekordbox import Rekordbox6Database
from rekordbox_edit.api import search
from rekordbox_edit.models import SearchArgs

db = Rekordbox6Database()
response = search(db, SearchArgs(artist=["Daft Punk"], format=["flac"], match_all=True))
for track in response.tracks:
    print(track.ID, track.Title)
```

`--print json` on any CLI command emits exactly these response envelopes, so the models below also document the JSON you get when scripting.

## Functions

::: rekordbox_edit.api.search

::: rekordbox_edit.api.edit

::: rekordbox_edit.api.convert

## Models

::: rekordbox_edit.models
