## v0.8.0 (2026-08-01)


- chore(deps): update dependency commitizen to v4.17.0 (#158)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- feat!: replace --exact-path with case-insensitive --resolved-path
- Path filters now always match case-insensitively, mirroring how NTFS
and APFS treat paths. --resolved-path makes its argument absolute by
pure string math instead of Path.resolve(), so results no longer
depend on mounted drives, on-disk casing, or symlinks.
- chore(deps): update pre-commit hook commitizen-tools/commitizen to v4.17.0 (#159)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: reduce renovate schedule to weekends
- docs: add FAQ about converts impact on USB exports
- chore(deps): update github actions (#151)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- ci: optimize the build_release_notes script

## v0.7.0 (2026-07-31)


- ci: more precise changelogs on releases
- chore: update AGENTS.md
- docs: pave FAQ page based on convert + analysis research
- feat(convert): verify source codec against FileType before converting
- test(cli): mock rekordbox pid check in edit CLI tests
- feat: add probe/file-type matcher and codec_mismatch skip reason
- feat(utils): probe codec and container in get_audio_info
- feat: adds display and filtering support for all rekordbox file types
- - creates a FileTypeInfo registry to map all the different dimensions of
  FileType under one database code
- adds AAC and ALAC .m4a FileTypes (4 and 6)
- adds .mp4 FileType (3)
- adds video FileType (16)
- chore(deps): update dependency ty to v0.0.64 (#152)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.16.0 (#149)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters (#148)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.11.0 (#147)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.62 (#145)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks (#146)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency pre-commit to v4.6.1 (#144)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update fkirc/skip-duplicate-actions digest to a09bf67 (#143)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.61 (#142)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update actions/checkout action to v7.0.1 (#141)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency platformdirs to v4.10.1 (#140)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency mkdocs-material to v9.7.7 (#139)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency commitizen to v4.16.5 (#138)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pypa/gh-action-pypi-publish digest to ba38be9 (#137)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update fkirc/skip-duplicate-actions digest to b974a93 (#136)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: ignore research/decision docs
- fix(convert): update FileSize, OrgFilePath cols; PPTH ANLZ tag
- refactor(convert): merge shared logic of ffmpeg helpers
- Replace _convert_to_hi_res and _convert_to_mp3 with a single _run_ffmpeg
runner and two pure output-kwargs builders.
- fix(convert): skip unsupported source formats via input whitelist
- Previously we were skipping via a blacklist, which allowed
unknown/unsupported formats to create undefined behavior.
- refactor(convert): change get_file_type_name a simple display map
- chore(deps): update dependency ty to v0.0.59 (#134)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.5.3 (#133)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency mkdocstrings to v1.0.6 (#132)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency mkdocstrings to v1.0.5 (#131)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update softprops/action-gh-release digest to 3d0d988 (#130)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters (#128)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.21 (#129)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.5.2 (#127)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8.3.2 (#126)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8.3.1 (#125)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.5.1 (#124)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update astral-sh/setup-uv action to v8.3.0 (#123)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.4.0 (#122)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.56 (#121)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update actions/checkout action to v7
- chore(deps): update dependency ty to v0.0.55 (#120)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.3.4 (#119)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters (#117)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hook astral-sh/ruff-pre-commit to v0.15.20 (#118)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.3.3 (#116)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.53 (#115)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency click to v8.4.2 (#114)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ruff to v0.15.19 (#112)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks (#113)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency ty to v0.0.52 (#111)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency commitizen to v4.16.4 (#110)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update github actions (#109)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update testing (#108)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.15.18 (#106)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks to v0.15.18 (#107)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.0.50 (#104)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update github actions to 718ea10 (#103)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update testing to v9.1.0 (#102)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.15.17 (#100)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update pre-commit hooks to v0.15.17 (#101)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.0.48 (#99)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update dependency syrupy to v5.3.2 (#97)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update linters to v0.0.46 (#98)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore: ruff formatting
- fix(convert): encode MP3 at the target bit depth and sample rate
- Pass ar=44100 and sample_fmt=s16p to libmp3lame instead of inheriting
the source rate, so MP3 output always matches the 16-bit/44.1 kHz
conversion target. MP3 ConvertOps report the target instead of None.
- fix(convert): update MP3 bit depth and sample rate in database
- Converting to MP3 left the source values (e.g. 24-bit/96 kHz) on the
record. Rekordbox stores MP3s as 16-bit with the real sample rate, per
the e2e database fixtures, so write those after conversion.
- feat(convert): report audio properties on ConvertOp
- Add source/output file type, bit depth, and sample rate fields so
dry-run previews and JSON output describe each conversion fully.
Source fields mirror the database record, the output sample rate
clamps to the source, and MP3 output leaves bit depth and sample rate
to the encoder.
- fix(convert): respect bit depth and sample rate between hi-res formats
- Hi-res conversions now explicitly target 16-bit/44.1 kHz. The target
sample rate clamps to the source so nothing is ever up-sampled,
down-sampled conversions count as lossy so --delete-originals lossless
keeps those originals, and the database record is updated with the
converted file's bit depth and sample rate.
- Fixes #92
- BREAKING(convert): replace --delete/--keep with --delete-originals enum
- The tri-state boolean becomes an explicit mode: 'none' never deletes,
'all' always deletes, 'lossless' (default) deletes only for hi-res
output formats. Also drops the unsupported 'alac' --format-out choice,
which crashed at conversion time.

## v0.6.0 (2026-06-12)


- chore(deps): update dependency mkdocstrings to v1
- ci: setup python via setup-uv to fix cache key collisions
- ci: validate conventional commits always, check PR titles
- docs: clean up documentation
- chore(deps): update linters to v0.0.45 (#90)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- refactor: rename CommandArgs types to CommandRequest
- docs: open external links in a new tab with an icon
- docs: render signatures and model fields in api reference
- docs: add api reference page
- docs: add convert command page
- docs: add edit command page
- docs: add search command page
- docs: add filtering page
- docs: configure read the docs build
- docs: scaffold mkdocs material site
- docs: trim README to overview and quick start
- chore: add docs dependency group
- feat: add --last filter to return only the last N results
- feat: add --first filter to return only the first N results
- test(e2e): update windows snapshot with unicode representation
- test(e2e): force utf-8 encoding of stdout
- test(e2e): align TZ to UTC
- test(ci): parameterize the db version as an env var
- ci(e2e): add windows-latest to the e2e matrix
- test: add windows snapshots for e2e journey
- test(e2e): parameterize snapshots by fixture DB
- Routes the two contract snapshots through SNAPSHOT_KEY (macos/windows)
so the Windows fixture can land its own snapshot alongside the macOS
one. Docker reuses the macOS DB and therefore the macos key.
Renames the existing snapshot entries to the [macos] variant.
- test: adds 6.8.6 db fixture for windows
- test(e2e): pretty-print JSON snapshots via JSONSnapshotExtension
- The single-line raw CLI output made snapshot diffs unreadable when a contract
field changed. Use syrupy's JSONSnapshotExtension for the search-json test:
the parsed payload is dumped as indented JSON to its own .json file under
__snapshots__/test_journey/, so post-update diffs land per-field.
- The IDs snapshot stays on AmberExtension; it's already one short line.
- ci(e2e): add macos-latest e2e job to the matrix and require it
- Adds a new e2e-tests job to ci.yml matrix'd over macos-latest × Python
{3.11, 3.14}, wiring it into the all-green aggregate so branch protection
gates on it. Windows joins in a follow-up PR once a windows master.db
fixture exists.
- The composite action at .github/actions/e2e/ installs ffmpeg on the runner,
sets RBE_RUN_E2E=1, and runs pytest against tests/e2e directly.
- test(e2e): add docker leg and make targets
- Local e2e validation runs through a Linux container; the conftest refuses to
run on bare macOS/Windows. `make test-e2e-docker` builds the image (Python
3.14 + ffmpeg + uv-synced project) and runs the journey suite;
`make test-e2e-snapshot-update` regenerates snapshots inside the container so
the host's working tree picks them up via the volume mount.
- `make test-e2e` runs the suite directly with uv; useful inside the container
itself or in CI runners where the platform check passes.
- test(e2e): add journey suite, conftest, and macOS snapshots
- A single ordered file walks search → edit → convert against the committed
macOS master.6.8.6.db, exercising filter narrowing, dry-run safety, stdin-pipe
edits, unicode metadata, and the convert row-swap. Snapshots lock the JSON
and IDs print contracts for `search`.
- The conftest gates the suite behind RBE_RUN_E2E=1 and refuses to run on
macOS/Windows outside CI, pointing local users at the Docker leg. The
canonical staging path is /private/tmp/rbedit-e2e/music — macOS resolves
/tmp through that symlink, so the DB stores the canonical form.
- Excludes tests/e2e/__snapshots__/ from the trailing-whitespace and
end-of-file pre-commit hooks; syrupy-generated whitespace is meaningful.
- test(e2e): register marker, exclude from default collection, add syrupy
- Adds the `e2e` pytest marker, sets `norecursedirs` so default `make test` runs
do not collect the suite, and pins syrupy>=5 for snapshot assertions.
- test: add macos 6.8.6 db fixture
- test(e2e): rename audio fixtures to property-encoded scheme
- Filenames now describe the audio's discriminating properties
(NN-<codec>-<rate>-<depth-or-bitrate>[-encmode].<ext>) so each file's purpose
is obvious in a directory listing and in test code. Codec stays in the name
even for unambiguous extensions to keep the convention uniform and to
disambiguate ALAC vs AAC inside .m4a.
- Required before Phase 3 (Rekordbox import) so master.db references the new
paths. Generator script and library table updated in gist
https://gist.github.com/jviall/18107ca35e0e7f38cf02ba50e3b9cc77
- test(e2e): add 10-track audio fixture for end-to-end suite
- Synthesized sine-wave audio covering FLAC (16/24-bit), ALAC, AIFF, WAV,
MP3 (CBR + VBR), AAC, and a unicode-tagged FLAC. Used by the e2e journey
suite (search/edit/convert) against the committed master.db fixtures.
- Bumps pre-commit's check-added-large-files threshold to 1 MB to admit the
WAV fixture (563 KB at 96 kHz / 24-bit / 2 s mono).
- Generator script and Phase 3 (Rekordbox import) instructions:
https://gist.github.com/jviall/18107ca35e0e7f38cf02ba50e3b9cc77
- fix(query): order results by folder, then ID, for stable output
- feat: adds global --database-path argument
- chore(deps): update linters to v0.0.44 (#79)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- test: restore coverage lost during api/cli redesign
- Restore tests for ffmpeg conversion internals, post-commit/rollback
paths, and the CLI preview-confirm-commit default flow that the
single-function API redesign dropped. Coverage recovers from 87% to
97% (baseline pre-redesign was 98%) and the test count from 200 to
238.
- refactor: privatize module-internal helpers and unify cli print helpers
- - api/convert.py: prefix module-private helpers with underscore
  (_convert_to_lossless, _convert_to_mp3, _update_database_record,
  _cleanup_converted_files, _rollback_and_cleanup, _get_output_path)
- cli/{edit,convert}.py: rename _render_*_response to _print_*_result
- fix(api,cli): fixups post refactor
- - convert(): on post-commit re-query failure, fall back to pre-mutation
  snapshot tracks instead of an empty list, so the response validator
  doesn't raise after a successful commit
- cli/convert.py: remove duplicate "Deleted N" log in the default flow
- cli/edit.py: log "No changes to make." in --yes path when no edits
- Adds a regression test for the post-commit re-query fallback.
- feat(api,cli)!: redesign around single-function commands
- Replace the plan/execute split with one function per command that takes
an optional dry_run kwarg. Each command (search, edit, convert) now
returns a typed response envelope with tracks plus a command-specific
result. CLI restructured to preview-then-commit by default and to call
the API exactly once when --yes or --dry-run is given.
- BREAKING CHANGE: drops plan_edit/plan_convert. The public API surface is
now search/edit/convert; old EditPlanArgs/ConvertPlanArgs types removed.
- feat: add new `--print json` option
- refactor: Allow extra columns to ride with Track instances
- chore(deps): update linters to v0.15.16 (#76)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- fix: handle stdin BOM character on windows
- chore(deps): update linters to v0.0.43 (#73)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- chore(deps): update github actions to v8.2.0 (#74)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>

## v0.5.0 (2026-06-06)


- ci: use workflow token
- chore(deps): update github actions (#71)
- Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>
- ci: fix canary release increment
- test: add tests to cover new modules
- test: add back convert tests that got dropped
- refactor: rename args.py to models.py
- feat: wire public API and delete legacy commands/
- - feat: expose public API from rekordbox_edit.__init__
- chore: remove tests/commands/ (replaced by tests/cli/)
- chore: remove commands/ and cli.py (replaced by api/ and cli/)
- fix: resolve typecheck and lint errors in api layer and tests
- feat: add api/ and cli/ packages
- - feat: add api/_utils.py with _track_from_content
- feat: update display.py to accept Track instead of DjmdContent
- refactor(display): remove redundant setup comments in tests
- feat: add api/search.py
- feat: add api/edit.py with plan_edit and edit
- feat: add api/convert.py with plan_convert and convert
- fix(convert): remove unused get_file_type_name import
- feat: add api/__init__.py re-exports
- feat: add cli/main.py and cli/__init__.py
- feat: add cli/_utils.py with shared confirmation helpers
- feat: add cli/search.py
- feat: add cli/edit.py
- feat: add cli/convert.py
- refactor: restructure args.py with Track model and API arg types
- - refactor: add Track model and EditPlanArgs/ConvertPlanArgs to args.py
- refactor: correct docstring layer count and strengthen test assertions
- feat!: drop support for python 3.10

## v0.4.0 (2026-06-05)


- Revert "bump: version 0.3.1 → 0.4.0"
- This reverts commit c353b3ae6b24793c6911a153b021267a16473d87.
- ci: improve canary release naming and skip duplicates
- ci: use same changelog config in both release types
- ci: fix releases
- bump: version 0.3.1 → 0.4.0
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
