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
