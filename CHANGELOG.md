## v0.4.0 (2026-06-05)


- chore(deps): update crazy-max/ghaction-import-gpg action to v7
- chore(deps): update github artifact actions
- chore(deps): update softprops/action-gh-release action to v3
- chore(deps): update testing
- fix(deps): update dependency rich to v15
- fix(display): Add min-width to print columns
- refactor(args): compose command args via Pydantic model   inheritance
- refactor(args): adopt Pydantic for component arg types
- refactor(commands): group command-specific args into EditArgs and ConvertArgs dataclasses
- refactor(commands): group confirmation flags into ConfirmationArgs dataclass
- docs: update README.md
- refactor(query): group filter args into FilterArgs dataclass
- refactor(cli): extract convert-specific options into convert_click_options
- refactor(cli): extract edit-specific options into edit_click_options
- refactor(cli): extract shared confirmation flags into global_click_confirmations
- chore(deps): update linters to v0.0.42 (#58)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- fix(display): Don't crash on unknown file type during print_track_info
- chore(deps): update commit tooling to v4.16.3 (#54)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks to v4.16.3 (#55)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.10.0 (#53)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ruff to v0.15.15 (#50)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.15 (#51)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.40 (#49)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8
- chore(deps): update actions/setup-python action to v6
- ci: clean up job skipping
- chore: add more groups to renovate config
- chore: exclude-newer for uv resolution to match renovate minimum age
- chore(deps): update dependency pre-commit to v4.6.0 (#39)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency commitizen to v4.16.2 (#38)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.14 (#37)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency click to v8.4.0 (#36)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.38 (#35)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ruff to v0.15.13 (#34)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): pin dependencies (#33)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: correct renovate config
- fix(display): split up the unified Location column into FolderPath and FileName
- docs: update AGENTS.md
- feat(display): add before/after change preview to print_track_info
- refactor(display): render print_track_info with rich.table.Table
- Replace the fixed-width f-string loop with a rich Table so column widths
adapt to content and embedded ANSI sequences no longer skew alignment.
PRINT_HEADERS becomes plain column labels (rich handles padding). Drain
the recorded output to the debug log after each render.
- refactor(display): extract print_track_info into display module
- Add rich dependency and move PrintableField, PRINT_WIDTHS, PRINT_HEADERS,
truncate_field, and print_track_info from utils to a new display module
with a module-level Console for upcoming rich-based rendering. Update
edit, convert, and search command imports. Move associated tests from
test_utils.py to test_display.py. Pure move; no behavior change.
- chore(deps): update pre-commit hooks (#29)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- feat(edit): add --multi to allow batch edits past single-track guard
- feat(edit): add --match for literal find/replace within field value
- Introduces a _compute_new_value helper and --match option so that
rbe edit can replace a substring of the current field value instead of
performing a wholesale replacement; None current values and non-matching
patterns are treated as no-ops.
- chore: add max-complexity lint rule
- docs: update AGENTS.md
- test: add coverage for --interactive + --yes skipping all confirms
- feat: adds edit command
- Adds an `edit` subcommand to the CLI with:
- Title field support via a required FIELD argument and --replace option
- Single-track safety guard that aborts when >1 track would be modified
- --dry-run mode that previews changes without writing to the database
- --yes flag to skip confirmation, --interactive to confirm per-track
- Scripting mode (--print=ids) requiring --yes or --dry-run
- Piped stdin rejection without --yes or --dry-run
- All global filter flags forwarded to get_filtered_content
- docs: add AGENTS.md with project conventions and CLAUDE.md symlink
- chore: add renovate config
- feat: Add --path and --exact-path search filters
- chore: add pytest-watcher and watch task in Make
- feat(CollectionQuery): add by_path query filter

## v0.3.1 (2026-04-17)


- chore: version bump 0.3.1
- ci: allow dispatching of publish workflow
- chore: big 'ol project rename cause it was too long
- docs: update readme and contributing
- chore: change commitizen config and providers to work with uv
- ci: skip CI and CD when no code-impacting changes have occurred
- docs: update readme

## v0.3.0 (2026-04-09)


- ci: add windows-latest + python 3.14 to CI matrix
- ci: Add typechecking with astral/ty
- ci: switch from poetry to uv cause I like shiny things
- tests: cover more edge cases and error paths
- fix: merge track_ids filter with other specified filters.
- - Also adds missing test cases for CollectionQuery and
  get_filtered_content
- documents scripting examples and adds AI disclaimer
- fix: improved debug logs
- fix: require --dry-run or --yes when piping track_ids
- feat: Add support for track_id arguments via STDIN for scripting
- refactor: Drop custom logger class
- feat: add debug as a PrintChoice option
- fix: drop unreachable code
- fix: match_all incorrectly set to method during query copy
- fix: add debug log folder to help output
- fix: normalize output paths
- docs: update readme
- feat(convert): add support for the print flag
- feat: refactor convert command to not suck and use the query class
- Big refactor. Huge. The convert command was some vibe-coded bs. Now it's
some vibe-coded nice stuff. Logs are much better. Way less nested
conditions, better inversion of control. Way less annoying UX.
- fix: verbose log query filters
- feat: create --print flag to specify program output preference
- feat: Add rbe command alias, update readme, and update deps
- feat: replace Read command with Search command using the CollectionQuery class
- refactor: print_track_info and related funcs
- refactor: pave new CollectionQuery class
- intended to act as a universal query builder that enables a unified set
of filters for all commands
- fix(deps): upgrade and pin pyrekordbox to 0.4.4
- fix: drop support for python 3.9
- ci: fix mismatched version of checkout action
- ci: continuously publish canary releases, selectivly publish stable releases
- ci: cleanup unused action input

## v0.2.7 (2025-08-19)


- ci: fix broken version-bump.yml
- ci: add codecov.yml config
- ci: fix codecov publishing
- fix: use a logger to separate log levels and output a log file to system user data folder
- ci: one final typo in publish.yml
- ci: don't validate empty commit ranges on main
- ci: Customize commit convention and validate during CI
- ci: fix publish workflow
- chore: fix version-bump workflow typo
- chore: add re-actors/alls-green action for easier status checks
- chore: fix workflows

## v0.2.6 (2025-08-10)

### Fix

- no default return on get_audio_info

## v0.2.5 (2025-08-02)

### Fix

- bug where convert command was trying to call .get on a function. Add happy path test cases for convert command
- use getter functions for the file type and extension maps

### Refactor

- drop psutils in favor of pyrekordbox.utils

## v0.2.4 (2025-08-01)

### Fix

- Filter out all m4a and mp3 targets

## v0.2.3 (2025-08-01)

### Fix

- Check if ffmpeg exists and if not point to installation.

## v0.2.2 (2025-08-01)

### Fix

- Attempt to fix broken paths on windows

## v0.2.1 (2025-07-31)

### Fix

- Add unit tests for utils and convert. Make is_rekordbox_running() more specific. Fix bad Error handling on ffmpeg

### Refactor

- clean up variables

## v0.2.0 (2025-07-31)

### Feat

- Add support for all audio types in read command, and converting between all lossless types in convert command
- Add support for all audio types in read command, and converting between all lossless types in convert command
- Add support for converting to MP3 320 CBR
- Convert project into a package
- Support confirmation message at each confirmation, and wait till end of program to commit changes
- rename rekordbox_reader.py to reader.py and add support for single file ID argument with get_track_info()
- Adds convert command to convert from FLAC to AIFF
- fuzzy match column names that may be relevant to file format
- read out all FLAC files with basic info
- hello world

### Fix

- Allow for output file to already exist but confirm to use
- Update bitrate after conversion from FLAC to AIFF
