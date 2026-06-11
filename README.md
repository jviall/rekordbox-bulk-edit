# rekordbox-edit

[![Build](https://img.shields.io/github/actions/workflow/status/jviall/rekordbox-edit/cd.yml?branch=main&logo=github&style=flat)](https://github.com/jviall/rekordbox-edit/blob/main/.github/workflows/cd.yml)
[![Coverage](https://codecov.io/gh/jviall/rekordbox-edit/graph/badge.svg?token=ILZ1XHE61V)](https://codecov.io/gh/jviall/rekordbox-edit)
[![Version](https://img.shields.io/pypi/v/rekordbox-edit?style=flat)](https://pypi.org/project/rekordbox-edit/)
[![Platforms](https://img.shields.io/badge/platform-win%20%7C%20osx-blue?style=flat)](https://pypi.org/project/rekordbox-edit/)
[![License](https://img.shields.io/pypi/l/rekordbox-edit?color=lightgrey)](https://github.com/jviall/rekordbox-edit/blob/main/LICENSE)

A command-line tool for bulk operations on your Rekordbox library. Search tracks, edit metadata, and convert audio formats — updating your database while preserving all your cues, analysis, and metadata.

> [!CAUTION]
> This tool can modify your Rekordbox database and audio files. Always back up your data first.
> No warranty is provided--you assume all risk and liability of data loss in using this.
> See [Safety and Best Practices](#safety-and-best-practices)

**Full documentation: [rekordbox-edit.readthedocs.io](https://rekordbox-edit.readthedocs.io/)**

## Installation

```bash
pip install rekordbox-edit
```

**Requirements:**

- Python 3.11+
- FFmpeg (for audio conversion)

## Quick Start

Search your library:

```bash
rbe search --artist "Daft Punk" --format flac
rbe search --playlist "House Favorites"
```

Edit track metadata:

```bash
# Fix a typo across every matching title (previews and confirms first)
rbe edit --title "Teh" Title --match "Teh" --replace "The" --multi
```

Convert audio files:

```bash
# Preview what would be converted
rbe convert --artist "Daft Punk" --dry-run

# Convert all FLAC or WAV files to AIFF (default output format)
rbe convert --format flac --format wav --yes
```

See the [documentation](https://rekordbox-edit.readthedocs.io/) for every command, the full filtering language, and scripting recipes.

## Safety and Best Practices

**Before using this tool:**

1. **Back up your Rekordbox database**

   Rekordbox already keeps multiple backups. But every time you close it, it creates a fresh one and deletes the oldest, so repetitive exits will quickly make those backups fairly useless.

   You should make manual copies of RB's database backups before using this. You can usually find them in `~/Library/Pioneer/rekordbox/` on macOS or `%APPDATA%\Pioneer\rekordbox\` on Windows.

2. **Back up your music library**

   If you don't have a back up already it's a very worthwhile investment, even if you don't plan to use this tool! Find yourself a cheap external drive, you won't regret it.

And generally limit the potential impact of a mistake by using filters to target a few tracks at a time e.g. `--artist "Crazy Frog" --first 5` before targeting a larger set, and always run with `--dry-run` first.

## AI Usage

I believe it's important to be aware of and to disclose AI usage. In many ways it's being forced upon us without us having much choice in the matter, and it's a gross and oppressive experience. While it has lots of potential to benefit the common good, mostly it's only furthered capitalist greed.

I'm mostly attempting to thoughtfully disclose that generative AI _has_ been a significant tool in building out this project. I don't personally enjoy too much coding in my personal time, but I feel passionate about making `rekordbox-edit`--AI has admittedly helped me bridge that gap between my capacity and my vision. I'm a career professional software engineer who takes pride in their work, and I don't want to produce a vibe coded mess any more than you want to experience it. Please validate the quality of this project yourself--at the end of the day it's just code written by some stranger.

If it's any consolation, my main test subject has been my own 10,000+ track RekordBox library--a risk I do not take lightly!

## Credits

This project exists thanks to [@dylanjones](https://github.com/dylanjones), the creator of [pyrekordbox](https://github.com/dylanljones/pyrekordbox), which provides the Python API for Rekordbox databases.

I built this tool to help correct my own bad habits and missteps in managing and organizing my rekordbox library. If it helps you too, great! If you find issues or have ideas, contributions are welcome.

## Contributing

See [CONTRIBUTING.md](https://github.com/jviall/rekordbox-edit/blob/main/CONTRIBUTING.md) for development setup, testing, and contribution guidelines.
