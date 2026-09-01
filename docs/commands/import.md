# import

Add audio files to your Rekordbox database that Rekordbox does not yet know about.

```bash
rbe import [OPTIONS] PATHS...
```

`PATHS` accepts files, directories, or a mix of both. `import` writes the same row shape Rekordbox itself writes when it imports a file it has not analyzed yet.

```bash
# Import a handful of files
rbe import "/Users/me/Music/track1.flac" "/Users/me/Music/track2.flac"

# Import an entire folder, confirming the walk interactively
rbe import "/Users/me/Music/New Tracks"

# Import a folder and place every new track in an existing playlist
rbe import "/Users/me/Music/New Tracks" --to-playlist "Recently Added" --yes
```

## What Gets Filled and What Does Not

`import` reads tags from each file: title, artist, album, genre, composer, label, track number, disc number, release year, comment, ISRC, and initial key. It also reads the file's duration and type. Title falls back to the file name when the file has no title tag.

It does not analyze audio. `SampleRate`, `BitDepth`, and `BPM` read as `0` on a freshly imported track, and stay that way until you select the track in Rekordbox and run analysis on it. Even if you have "Auto Analysis" enabled, tracks imported with rekordbox-edit will need to be manually analyzed inside Rekordbox.

## Playlists

`--to-playlist NAME` places every imported track in an existing playlist, matched case-insensitively. It does not currently support creating a playlist that does not exist, and will error if it can't find the playlist you provided.

A file that already has a row in the library but is missing from the named playlist is added to that playlist rather than skipped outright.

## Directories

A directory argument is walked recursively for audio files. Ran interactively, `import` reports how many files it found and asks you to confirm before continuing. `--yes` authorizes the walk outright, and is required when providing a non-interactive `--print` mode and a directory argument. `--dry-run` also walks without asking, since it writes nothing and previewing is how you inspect what a walk covers.

The walk happens once, before the preview. A file dropped into the directory while you are answering the prompt is not imported, since `import` writes exactly the files it showed you.

## Skipped Files

A file already in the library, matched by its resolved, case-insensitive path, is skipped rather than duplicated. One that cannot be read as audio, or that is not an audio file at all, is skipped with a warning, and the rest of the batch continues. A file that disappears between the preview and the write is skipped too.

## Checks

- Without flags, `import` shows every track it plans to add and asks once before writing; `--interactive` asks about each file separately; `--dry-run` previews without writing; `--yes` confirms the default choice for all prompts without asking. `--interactive` cannot be combined with `--yes` or `--dry-run`.
- **Rekordbox running:** writing while Rekordbox is open risks losing your changes, so `import` refuses at the point it would write. The preview still runs, so an interactive run reports the refusal after you confirm. `--dry-run` is unaffected.

## Reference

<!-- prettier-ignore -->
::: mkdocs-click
    :module: rekordbox_edit.cli.import_
    :command: import_command
    :prog_name: rbe import
    :depth: 1
