# Frequently Asked Questions

Messing with your Rekordbox library is bound to raise some questions and concerns, particularly around preserving all the manual work you've done to organize, catalog, and prepare your library for gigs. This page is dedicated to answering those questions around what the impact and risks are of editing your rekordbox library or the underlying audio files using rekordbox-edit. If your question isn't answered here, please ask it in [a discussion](https://github.com/jviall/rekordbox-edit/discussions/new/choose).

## How does Rekordbox's analysis work?

Analysis touches two places in your library. The database gets the summary values for things like tempo, key, and the flags Rekordbox uses to track analysis state. The heavier artifacts live in a per-track folder of analysis files (.ANLZ) containing the beat grid, waveforms, and phrase data. Your cues and loops live in neither; they are separate database records that only your own edits change.

What analysis writes is a deterministic estimate. Deterministic, because the same file analyzed twice produces byte-identical results. An estimate, because tempo, grid, and key are inferred from the audio, and Rekordbox's inference is sometimes wrong. Both aspects are worth considering; when the analysis of a converted file produces a different result, it is simply a different estimate from different data.

## How does converting a track affect its analysis?

The reason conversion is safe comes down to how Rekordbox stores analysis: positions are timestamps. The beat grid is a list of times in milliseconds, cues are stored in milliseconds, and phrases are anchored to beats. None of it references sample counts or byte positions in the audio file. Change the codec, the sample rate, or the bit depth, and every stored position still names the same musical moment.

`rbe convert` therefore only has to update what identifies the file: the track's database row (the file path, sample rate, bit depth, and similar columns) and the path recorded inside the analysis files. It rewrites nothing else.

There are a few minor things left stale by a conversion (without any consequence that I have observed yet):

- The waveform still draws the old audio: identical unless you converted to MP3, and then only imperceptibly off.
- A FLAC-specific seek index goes stale when you convert away from FLAC, which would be removed on any later analysis.

Converting _to_ FLAC does not create that seek index automatically either; only an analysis can. I have _not_ tested (yet) whether that matters in practice, but it makes a stronger case for re-analyzing after a conversion to FLAC than for other targets. FLAC also is not the most ideal target format in general for Rekordbox (even though it's preferred for streaming and music hoarders), because only the more recent Pioneer devices support it (this may or may not be the original reason I built this tool....:p). AIFF is what I would pick if you insist on lossless.


## Does changing the source file impact cues or beatgrids?

As long as it is the same song, with no difference in the original's underlying samples or length, no. Cues, loops, and memory points are records in your library database, positioned in milliseconds and attached to the track's database entry, and `rbe convert` does not touch them. The beat grid lives in the analysis files, which convert also leaves alone. In all my testing, every cue and beat grid has been completely unchanged by a conversion, and works just as it did prior.

This includes hand-tuned grids. Because convert never rewrites the grid a manually corrected beat grid survives conversion unchanged. The one operation that can replace it is a re-analysis you run yourself; see below.

So The only artifact of a conversion/path edit, is typically the visual waveform in Rekordbox--the drawn waveform still reflects the lossless original rather than the MP3. A re-analysis would redraw it, but you'd be hard-pressed to notice the difference.

## Should I re-analyze after converting?

You do not need to. The existing analysis remains correct for the converted file, and Rekordbox never re-analyzes on its own; it waits for you to ask. Skipping re-analysis keeps your grid and cues exactly as they are.

If you do re-analyze, the outcome depends on whether the conversion changed the audio samples. A pure container swap (WAV to FLAC or AIFF at the same depth and rate) reproduces the previous analysis exactly. A conversion that resamples, reduces bit depth, or lossily compresses to MP3 produces a slightly different estimate: e.g. about half a BPM of tempo difference, a first beat shifted by tens of milliseconds, cues sitting up to roughly 20 ms off the new grid. The new grid is not necessarily more or less correct than the previous; your ears and eyes will be the best judges of that. Ultimately it is the same song being analyzed, but Rekordbox made a fresh estimate on different underlying data. I would argue, though, that an analysis of a high-res file is more likely to be accurate than one of a lower-fidelity encoding.

> [!WARNING]
> Re-analysis _will_ replace manually edited beat grids on any track that is not locked. If you plan to re-analyze after a bulk conversion, turn on Analysis Lock first for tracks whose grids you have tuned by hand.

## What if I convert a track that's been exported to a USB?

Conversion only touches your library and the source file--it won't update your USB exports for you. The old version of the track that's on your USB will effectively be orphaned from the library. Depending on the library type (i.e. "Device Library" v.s. "One Device Library") re-syncing will either not do anything, or it will add your new converted versions but leave the stale copies behind. Manually transferring a playlist to a device and overwriting it (by drag-n-dropping in the library explorer tree) will also only add your new versions but not remove the old ones.

Perhaps a more crucial consequence of this orphaning of converted files on your USB, is that any cues, play counts, or other metadata of the converted files that is only on your USB and hasn't been synced back to Rekordbox will also be orphaned, and attempting to sync this back after a conversion won't work.

> [!TIP]
> If you're planning on doing an in-place conversion of tracks in your library using this tool, you should consider making sure the cues, grid, and info on your USB sticks has been synced back to Rekordbox (if so desired), and be prepared to erase and freshly export your USBs in order to avoid any stale files left behind by a re-export.

## What should I do before converting?

- **Preview with `--dry-run`.** See exactly which tracks will convert and where the files will go before anything is written.
- **Close Rekordbox.** This tool will not let you write to the database while Rekordbox is open.
- **Make fresh backups of your music and your Rekordbox database.** Conversion rewrites files and database rows in place; a current backup makes any mistake reversible.
- **Sync back cues, grids, and info from your USBs** Converting a track that has been exported will orphan the exported version and any un-synced metadata from your library.
- **Keep your originals until you are satisfied.** The default `--delete-originals lossless` only deletes a source when no audio information was lost. Be deliberate before choosing `all`.
- **Lock hand-tuned beat grids if you plan to re-analyze.** Conversion won't mess with your grids, but a later bulk re-analysis replaces grids on unlocked tracks. Analysis Lock exists for exactly this.

> [!TIP]
> Rekordbox creates backups of its own database every time you close it. It keeps 2 backups at a time, and deletes the oldest. You should not rely on these backups for this reason, since your back up will only be as old as your third-most-recent session. Make your own copy of the database before running `rekordbox-edit`.

## Can I run two rekordbox-edit commands at once?

Yes, but any command that writes to the database holds a lock for its whole run, and a concurrent `rbe` will wait up to 30 seconds for that lock before giving up. An interactive invocation (i.e. no `--print` mode of `json`, `ids`, or `silent`) will never wait: it exits immediately if another process is already running.

Reads (a `search` or any other command with `--dry-run`) are not impacted by the database lock.
