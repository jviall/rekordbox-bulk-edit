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
