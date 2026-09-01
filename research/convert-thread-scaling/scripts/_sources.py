"""Shared fixture generation for the thread-scaling probes.

The committed e2e audio fixtures are two seconds long, far too short to measure
anything but process startup. These probes synthesize realistic track lengths
instead.
"""

import shutil
import subprocess
from pathlib import Path

#: Eight five-minute tracks: long enough that per-process startup disappears
#: into the measurement, small enough to run in seconds.
COUNT = 8
SECONDS = 300


def make_sources(work: Path) -> list[Path]:
    """Fresh FLAC sources under `work`, replacing anything already there.

    Pink noise rather than silence or a tone, so the FLAC decode does
    representative work. These compress to roughly 43%, near the 50 to 60% a
    real music library sees.
    """
    shutil.rmtree(work, ignore_errors=True)
    (work / "src").mkdir(parents=True)
    (work / "out").mkdir(parents=True)

    sources = []
    for i in range(COUNT):
        dst = work / "src" / f"track{i}.flac"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anoisesrc=d={SECONDS}:c=pink:r=44100",
                "-ac",
                "2",
                "-sample_fmt",
                "s16",
                str(dst),
            ],
            check=True,
            capture_output=True,
        )
        sources.append(dst)
    return sources
