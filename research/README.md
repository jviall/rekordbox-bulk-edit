# Research

In-depth research and findings on Rekordbox behaviors, facilitated by Claude. This
directory is a reference for maintainers: it records how Rekordbox stores and
mutates its library, analysis, and export data, and grounds the decisions the
`rbe` commands rest on. It is not linked from the documentation site and is not
referenced by the application code.

Each subfolder is one investigation, self-contained:

- `<task>.md` and supporting write-ups — the summary findings.
- `scripts/` — the read-only probes that produced the evidence.
- `evidence/` — the raw snapshots and dumps each claim cites.
- `decisions/` — the decision records the findings settle.

Shared tooling used by more than one investigation lives in `shared/scripts/`.

## Document Structure

Research write-ups follow a formal structure, using the sections that apply:
**Question** (the behavior under investigation and why it matters), **Hypothesis**
(the expected behavior, stated before testing), **Method** (fixtures, scripts, and
procedure), **Findings** (what the evidence shows, each claim tied to an evidence
file), and **Conclusion** (the practical implication for the tool). The prose is
formal and terse, and states findings as the evidence supports them.

## Investigations

- **`convert-reanalysis-impact/`** — what a `convert` run does to a track's
  analysis (the `DjmdContent` row, `DjmdCue` rows, and on-disk ANLZ files), why
  re-analysis rather than conversion is what moves a beat grid, and how far the
  analysis drifts across codecs and resolutions.
- **`convert-export-impact/`** — what `convert` does to a track already on a USB
  export, and why converting a track after export silently breaks re-export and
  sync-back on both legacy PDB and Device Library Plus players.
- **`edit-relational-fields/`** — how Rekordbox reassigns the shared `DjmdArtist`
  and `DjmdAlbum` records on an inline artist or album edit, and where the `edit`
  command deliberately diverges from that behavior.
- **`file-types/`** — how `convert` and the display layer should treat Rekordbox
  `FileType` codes the tool does not map.
