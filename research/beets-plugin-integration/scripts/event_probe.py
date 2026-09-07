#!/usr/bin/env python3
"""Record which beets events fire, in what order, and with which arguments.

Builds a throwaway beets library in a temp directory, installs a plugin that
listens to every event in `beets.plugins.EventType` plus the convert plugin's
undeclared `after_convert`, runs an import, and prints the observed sequence.

Autotagging is off so the probe needs no network and no MusicBrainz responses;
the event surface under `-A` is itself one of the questions.

Usage: event_probe.py <audio-file>... [--convert] [--reimport]
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

PROBE_PLUGIN = '''
import os
from beets.plugins import BeetsPlugin, EventType
from typing import get_args

# `after_convert` is sent by beetsplug/convert.py but is absent from EventType.
EVENTS = list(get_args(EventType)) + ["after_convert"]

LOG = os.environ["PROBE_LOG"]


def _short(v):
    if isinstance(v, bytes):
        return os.path.basename(v.decode("utf-8", "replace"))
    name = type(v).__name__
    if name in ("Item", "Album"):
        return f"{name}(id={getattr(v, 'id', None)})"
    if name in ("ImportTask", "SingletonImportTask"):
        return f"{name}(n={len(getattr(v, 'items', []) or [])})"
    if name.endswith("Session") or name == "Library":
        return name
    return name


class ProbePlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        for event in EVENTS:
            self.register_listener(event, self._make(event))

    def _make(self, event):
        def handler(**kwargs):
            args = " ".join(f"{k}={_short(v)}" for k, v in sorted(kwargs.items()))
            with open(LOG, "a") as fh:
                fh.write(f"{event}\\t{args}\\n")
        return handler
'''

CONFIG = """\
directory: {lib}
library: {db}
pluginpath: {plugdir}
plugins: probe{extra_plugins}
import:
  copy: yes
  write: yes
  autotag: no
  quiet: yes
ignore_hidden: yes
threaded: yes
paths:
  default: $albumartist/$album/$track $title
  singleton: Singles/$artist/$title
{convert_block}
"""

CONVERT_BLOCK = """\
convert:
  auto_keep: yes
  dest: {dest}
  format: mp3
  formats:
    mp3:
      command: ffmpeg -v error -i $source -y -vn -acodec libmp3lame -b:a 320k $dest
      extension: mp3
"""


def run(sources, use_convert, reimport):
    root = tempfile.mkdtemp(prefix="beets-probe-")
    try:
        lib = os.path.join(root, "lib")
        plugdir = os.path.join(root, "plugins")
        inbox = os.path.join(root, "inbox")
        dest = os.path.join(root, "converted")
        for d in (lib, plugdir, inbox, dest):
            os.makedirs(d, exist_ok=True)

        with open(os.path.join(plugdir, "probe.py"), "w") as fh:
            fh.write(PROBE_PLUGIN)

        for src in sources:
            shutil.copy2(src, inbox)

        cfg = CONFIG.format(
            lib=lib,
            db=os.path.join(root, "library.db"),
            plugdir=plugdir,
            extra_plugins=" convert" if use_convert else "",
            convert_block=CONVERT_BLOCK.format(dest=dest) if use_convert else "",
        )
        beetsdir = os.path.join(root, "beetsdir")
        os.makedirs(beetsdir, exist_ok=True)
        with open(os.path.join(beetsdir, "config.yaml"), "w") as fh:
            fh.write(cfg)

        log = os.path.join(root, "events.log")
        env = {**os.environ, "BEETSDIR": beetsdir, "PROBE_LOG": log}

        def _import(label, args):
            open(log, "w").close()
            proc = subprocess.run(
                ["beet", "import", *args], env=env,
                capture_output=True, text=True,
            )
            print(f"\n=== {label} (exit {proc.returncode}) ===")
            if proc.returncode != 0:
                print(textwrap.indent(proc.stderr.strip()[:800], "    "))
            seen = []
            for line in open(log):
                event, _, args_ = line.rstrip("\n").partition("\t")
                seen.append((event, args_))
            width = max((len(e) for e, _ in seen), default=0)
            for i, (event, args_) in enumerate(seen, 1):
                print(f"  {i:3d}. {event:{width}s}  {args_}")
            print(f"  -- {len(seen)} events, "
                  f"{len({e for e, _ in seen})} distinct")
            return seen

        _import("import -A", ["-q", inbox])
        if reimport:
            _import("reimport (beet import -L)", ["-q", "-L", "path::."])
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("sources", nargs="+")
    p.add_argument("--convert", action="store_true")
    p.add_argument("--reimport", action="store_true")
    a = p.parse_args()
    if not shutil.which("beet"):
        sys.exit("beet not on PATH")
    run(a.sources, a.convert, a.reimport)
