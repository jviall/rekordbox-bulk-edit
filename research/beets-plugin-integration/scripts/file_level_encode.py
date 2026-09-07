#!/usr/bin/env python3
"""Can rekordbox-edit encode a file with no `DjmdContent` row in play?

`_encode_one` is documented as touching no database state. This builds
`_EncodeJob` by hand from a path on disk, the way a beets plugin holding an
`Item` would have to, and runs the encode. It also runs the job twice per
file: once declaring the source file type the way a rekordbox row does, and
once declaring `None` the way a caller with no rekordbox row can only do.

Run in the rekordbox-edit environment: `uv run scripts/file_level_encode.py <file>...`
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from rekordbox_edit.api._convert import _EncodeJob, _encode_one, _temp_output_path
from rekordbox_edit.utils import (
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
)

OUTPUT_FORMAT = "AIFF"


def job_for(source: str, out_dir: str, file_type: int | None) -> _EncodeJob:
    """The values `_encode_job_for` copies off a content row, supplied from the
    file itself instead. `track` is left unset: it only travels into a skip
    report, so a caller with no `DjmdContent` row can omit it."""
    output = os.path.join(
        out_dir, Path(source).stem + get_extension_for_format(OUTPUT_FORMAT)
    )
    return _EncodeJob(
        source_path=source,
        file_name=os.path.basename(source),
        file_type=file_type,
        output_path=output,
        temp_path=_temp_output_path(output),
        output_format=OUTPUT_FORMAT,
    )


def declared_type(source: str) -> int | None:
    """The rekordbox FileType code for this file, from its extension."""
    return get_file_type_for_format(Path(source).suffix.lstrip(".").upper())


def run(label: str, job: _EncodeJob) -> None:
    result = _encode_one(job)
    if result.skipped:
        print(f"  {label:16s} skipped: {result.skipped.reason}")
        return
    os.replace(job.temp_path, job.output_path)
    info = result.probe.audio_info
    print(
        f"  {label:16s} encoded: {os.path.basename(job.output_path)} "
        f"codec={info['codec']} {info['sample_rate']}Hz "
        f"{info['bit_depth']}bit lossless={result.is_lossless} "
        f"bytes={result.probe.file_size}"
    )


def main(sources: list[str]) -> None:
    out_dir = tempfile.mkdtemp(prefix="rbe-file-encode-")
    try:
        for source in sources:
            info = get_audio_info(source)
            print(
                f"{os.path.basename(source)} "
                f"(codec={info['codec']} {info['sample_rate']}Hz "
                f"{info['bit_depth']}bit)"
            )
            run("declared type", job_for(source, out_dir, declared_type(source)))
            run("file_type=None", job_for(source, out_dir, None))
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not on PATH")
    main(sys.argv[1:])
