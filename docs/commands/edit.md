# edit

Bulk-edit a metadata field on tracks in your Rekordbox database.

```bash
rbe edit [OPTIONS] [TRACK-IDS]... FIELD
```

`FIELD` specifies the [DjmdContent](https://pyrekordbox.readthedocs.io/en/latest/formats/db6.html#djmdcontent) column to change. Currently `Title` is the only editable field; more are planned.

`--replace` supplies the new value. On its own it overwrites the whole field; add `--match PATTERN` to find that literal text within the field and replace only that portion:

```bash
# Rename one track outright
rbe edit --exact-title "Untitled 3" Title --replace "Acid Rain"

# Fix a typo across many titles (substring replacement)
rbe edit --title "Teh" Title --match "Teh" --replace "The" --multi
```

## Guardrails

- **Preview and confirm by default.** Without flags, `edit` shows every planned change and asks once before applying. `--interactive` confirms each track individually; `--dry-run` previews without writing; `--yes` confirms the default choice for all prompts without asking.
- **Single-track by default.** When filters match more than one track, `edit` refuses unless you pass `--multi`. This prevents an unintentionally broad filter from making unintended edits across your library.
- **Rekordbox running:** editing while Rekordbox is open risks corrupting your database. By default `edit` warns; in a non-interactive mode (e.g. `--print ids`) it throws an error.

## Examples

```bash
# Preview a cleanup without touching the database
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --multi --dry-run

# Apply it, confirming each track
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --multi --interactive

# Pipe a search result in and edit those exact tracks
rbe search --playlist "Mislabeled" --print ids | rbe edit Title --match "  " --replace " " --multi --yes
```

See [Filtering](../filtering.md) for the full filter language.

## Reference

::: mkdocs-click
    :module: rekordbox_edit.cli.edit
    :command: edit_command
    :prog_name: rbe edit
    :depth: 1
