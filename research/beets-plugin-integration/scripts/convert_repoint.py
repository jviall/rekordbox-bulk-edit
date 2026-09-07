#!/usr/bin/env python3
"""What does a beets library need in order to follow an `rbe convert`?

`rbe convert` writes its output beside the source, keeping the stem and
changing the extension, and repoints the rekordbox row at it. This asks what
the beets side of that looks like:

- whether the path rbe chose is already where beets wants the file, under a
  path template that ignores the format and under one that does not;
- whether repointing an item (`item.path = new; item.read(); item.store()`,
  the pattern the convert plugin uses for `--keep-new`) keeps the item id,
  refreshes the audio properties, and preserves flexible attributes;
- what `Item.from_path` plus `Library.add` produces when the original is kept
  and the transcode has to be registered as a second item.

Builds its own library in a temp directory. Autotagging is off, so no network.

Usage: convert_repoint.py [--albums] <lossless-source> <hi-res-source>

`--albums` imports as an album rather than as singletons, which is what
decides whether a newly registered transcode can inherit an album.
"""

import os
import shutil
import subprocess
import sys
import tempfile

CONFIG = """\
directory: {lib}
library: {db}
import:
  copy: yes
  autotag: no
  quiet: yes
  singletons: {singletons}
paths:
  default: $artist/$title
  singleton: $artist/$title
"""

# The ffmpeg invocation rekordbox-edit uses for AIFF output at the conversion
# target (`_hi_res_output_kwargs` in rekordbox_edit/api/_convert.py).
FFMPEG_AIFF = [
    "-acodec", "pcm_s16be", "-ar", "44100",
    "-map_metadata", "0", "-write_id3v2", "1",
]

INNER = r'''
import os, sys
import beets.ui
from beets import config
from beets.library import Item
from beets.util import bytestring_path, displayable_path

# Open the library the way the CLI does, so the path templates and library
# directory come from the same config the import ran under.
config.read()
lib = beets.ui._open_library(config)
# The template a library keyed on format would use, for comparison only.
FORMAT_KEYED = [("default", "$artist/$format/$title")]

def show(label, item):
    print(f"  {label:22s} id={item.id:<3d} format={item.format:<6s} "
          f"bitrate={item.bitrate:<7d} samplerate={item.samplerate} "
          f"length={item.length:.2f}")

ROOT = os.path.realpath(displayable_path(lib.directory)) + "/"

def rel(path):
    return os.path.realpath(displayable_path(path)).replace(ROOT, "")

items = sorted(lib.items(), key=lambda i: i.path)
for n, item in enumerate(items):
    src = displayable_path(item.path)
    out = os.path.splitext(src)[0] + ".aiff"
    print(f"{os.path.basename(src)}")
    show("before", item)
    print(f"    rbe output path      {rel(bytestring_path(out))}")

    # Where beets would put the file once the item names the .aiff. The
    # extension comes from `item.filepath.suffix`, so the item has to be
    # pointing at the output before its destination means anything.
    source_path = item.path
    item.path = bytestring_path(out)
    default_dest = item.destination()
    keyed_dest = item.destination(path_formats=FORMAT_KEYED)
    item.path = source_path
    print(f"    beets destination    {rel(default_dest)}")
    print(f"    match (default)      {default_dest == bytestring_path(out)}")
    print(f"    beets destination    {rel(keyed_dest)}  (paths keyed on $format)")
    print(f"    match ($format)      {keyed_dest == bytestring_path(out)}")

    if n == 0:
        # Original deleted: repoint the existing item, as the convert plugin
        # does for --keep-new.
        item.rbe_probe_flexattr = "kept?"
        item.comments = "db-only edit, never written to the file"
        item.store()
        item.path = bytestring_path(out)
        item.read()
        item.store()
        reloaded = lib.get_item(item.id)
        show("after repoint", reloaded)
        print(f"    path                 {rel(reloaded.path)}")
        print(f"    flexattr preserved   "
              f"{reloaded.get('rbe_probe_flexattr') == 'kept?'}")
        print(f"    db-only comments     {reloaded.comments!r}")
    else:
        # Original kept: register the transcode as its own item.
        added = Item.from_path(bytestring_path(out))
        lib.add(added)
        show("added item", added)
        print(f"    path                 {rel(added.path)}")
        print(f"    album_id             {added.album_id} "
              f"(original's is {item.album_id})")
        print(f"    original still there {lib.get_item(item.id) is not None}, "
              f"id={item.id}")
    print()

print(f"items in library: {len(list(lib.items()))}")
'''


def beets_python() -> str:
    """The interpreter beets runs under, read from the `beet` shebang."""
    beet = shutil.which("beet")
    if beet:
        with open(beet, "rb") as fh:
            line = fh.readline()
        if line.startswith(b"#!"):
            candidate = line[2:].strip().decode()
            if os.path.exists(candidate):
                return candidate
    return sys.executable


def convert_beside(path: str) -> str:
    """Transcode to AIFF beside the source, the way `rbe convert` does."""
    out = os.path.splitext(path)[0] + ".aiff"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-i", path, *FFMPEG_AIFF, out],
        capture_output=True, check=True,
    )
    return out


def main(sources: list[str], singletons: bool) -> None:
    print(f"── imported as {'singletons' if singletons else 'an album'} "
          f"{'─' * 40}\n")
    root = tempfile.mkdtemp(prefix="beets-repoint-")
    try:
        lib, inbox, bd = (os.path.join(root, d) for d in ("lib", "inbox", "bd"))
        for d in (lib, inbox, bd):
            os.makedirs(d)
        for src in sources:
            shutil.copy2(src, inbox)
        db = os.path.join(root, "library.db")
        with open(os.path.join(bd, "config.yaml"), "w") as fh:
            fh.write(CONFIG.format(
                lib=lib, db=db, singletons="yes" if singletons else "no"))
        env = {**os.environ, "BEETSDIR": bd}

        subprocess.run(["beet", "import", "-q", inbox], env=env,
                       capture_output=True, check=True)

        paths = subprocess.run(
            ["beet", "ls", "-f", "$path"], env=env,
            capture_output=True, text=True, check=True,
        ).stdout.split("\n")
        for path in filter(None, paths):
            convert_beside(path)

        inner = os.path.join(root, "inner.py")
        with open(inner, "w") as fh:
            fh.write(INNER)
        run = subprocess.run([beets_python(), inner], env=env,
                             capture_output=True, text=True)
        print(run.stdout, end="")
        if run.returncode:
            print(run.stderr, file=sys.stderr)
            sys.exit(run.returncode)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    if not shutil.which("beet"):
        sys.exit("beet not on PATH")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not on PATH")
    args = [a for a in sys.argv[1:] if a != "--albums"]
    main(args, singletons="--albums" not in sys.argv[1:])
