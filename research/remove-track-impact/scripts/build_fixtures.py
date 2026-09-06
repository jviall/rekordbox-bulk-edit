"""Build the disposable subjects the removal arms operate on.

Copies real audio out of the collection into a staging directory and retags each
copy with a name no other track in the library uses. The study then imports the
copies, so every arm removes a track that exists only for the study and whose
shared artist, album, and genre records are reachable from nothing else.

    uv run python research/remove-track-impact/scripts/build_fixtures.py

Idempotent: it rebuilds the staging directory from scratch each run, which is
also how an arm that deleted a source file gets it back.

Six subjects. F1 and F4 each own their artist and album outright, so removing
one orphans those records and the arm can watch whether rekordbox collects them.
F2 and F3 deliberately share an artist and an album with each other, so removing
F2 leaves both records still referenced, which is the control showing that
collection follows the reference count rather than the removal. F4 is left
unanalyzed on purpose, to exercise the empty AnalysisDataPath path.

F5 and F6 were added after the first four arms, to close the two questions those
arms left open. They sit on one album and carry byte-identical cover art, so the
pair reveals whether rekordbox gives such tracks a shared ImagePath or separate
artwork directories. F5 alone carries a label, which no earlier fixture had, so
removing it shows whether an orphaned DjmdLabel is collected like an artist,
album, and genre are.

The tags carry the `RBE Remove Fixture` prefix so a leftover subject is
recognizable in the library at a glance, and so a search for that prefix finds
every row the study created.
"""

import shutil
import sys
from pathlib import Path

import mutagen
from mutagen.id3 import ID3, APIC, TPUB

STAGING = Path("/private/tmp/rbe-remove-fixtures")

#: Cover art stamped byte-identically into F5 and F6, lifted from a real file.
#: Identical bytes are the point: whether rekordbox gives two tracks on one
#: album with the same art a shared ImagePath or two separate artwork
#: directories is the question F5 and F6 exist to answer.
SHARED_ART_SOURCE = (
    "/Volumes/GIG MUSIC/Contents/Kanye West/Get Well Soon.._/"
    "23 - Reebok Commercial (feat. Scarface).mp3"
)

#: label -> (source file, title, artist, album, genre)
FIXTURES = {
    "F1": (
        "/Volumes/GIG MUSIC/Contents/Beastie Boys/Paul's Boutique/09 - 5-Piece Chicken Dinner.flac",
        "RBE Remove Fixture Alpha",
        "RBE Remove Fixture Artist Alpha",
        "RBE Remove Fixture Album Alpha",
        "RBE Remove Fixture Genre Alpha",
    ),
    "F2": (
        "/Volumes/GIG MUSIC/Contents/Gorillaz/Demon Days/01 - Intro.mp3",
        "RBE Remove Fixture Beta",
        "RBE Remove Fixture Artist Shared",
        "RBE Remove Fixture Album Shared",
        "RBE Remove Fixture Genre Shared",
    ),
    "F3": (
        "/Volumes/GIG MUSIC/Contents/Janelle Monae/Dirty Computer/12-janelle_monae-stevies_dream-repack-bd28a7.mp3",
        "RBE Remove Fixture Gamma",
        "RBE Remove Fixture Artist Shared",
        "RBE Remove Fixture Album Shared",
        "RBE Remove Fixture Genre Shared",
    ),
    "F4": (
        "/Volumes/GIG MUSIC/Contents/Childish Gambino/The Great Gambino/15 Twistclip Loop.mp3",
        "RBE Remove Fixture Delta",
        "RBE Remove Fixture Artist Delta",
        "RBE Remove Fixture Album Delta",
        "RBE Remove Fixture Genre Delta",
    ),
    "F5": (
        "/Volumes/GIG MUSIC/Contents/Frank Ocean/Cayendo/Frank Ocean - Cayendo (Sango Remix).mp3",
        "RBE Remove Fixture Epsilon",
        "RBE Remove Fixture Artist Art",
        "RBE Remove Fixture Album Art",
        "RBE Remove Fixture Genre Art",
    ),
    "F6": (
        "/Volumes/GIG MUSIC/Contents/Mac Miller/GO_OD AM/01 Doors.mp3",
        "RBE Remove Fixture Zeta",
        "RBE Remove Fixture Artist Art",
        "RBE Remove Fixture Album Art",
        "RBE Remove Fixture Genre Art",
    ),
}

#: F5 alone carries a label, so removing it orphans that DjmdLabel outright.
#: No earlier fixture had one, which left label collection the only behavior in
#: the command inferred rather than measured.
LABELS = {"F5": "RBE Remove Fixture Label Epsilon"}

#: Both share the album, so removing F5 leaves the album, artist, and genre
#: referenced by F6. Only the label and the artwork are at stake.
SHARED_ART = ("F5", "F6")

#: An album directory whose cover art sits beside the audio as cover.jpg rather
#: than inside it, which is how a large share of real libraries are organized.
#: The question is where rekordbox points ImagePath: at a copy under the share
#: tree, or at this file. If it is this file, then deleting "the track's
#: artwork" would delete something in the user's own music directory that every
#: other track in the album depends on, and `remove` must never touch it.
#: Both copies have their embedded art stripped, so folder art is the only art
#: available. Neither carries a label, so this pair cannot disturb the label
#: census the R6 removal reads.
FOLDER_ART_DIR = "rbe-folder-art-album"
FOLDER_ART = {
    "F7": (
        "/Volumes/GIG MUSIC/Contents/Ariana Grande/Sweetener/14. pete davidson.mp3",
        "RBE Remove Fixture Eta",
    ),
    "F8": (
        "/Volumes/GIG MUSIC/Contents/Pablo J & The Lobsterettes/Last Night/Last Night.mp3",
        "RBE Remove Fixture Theta",
    ),
}
FOLDER_ART_ARTIST = "RBE Remove Fixture Artist Folder"
FOLDER_ART_ALBUM = "RBE Remove Fixture Album Folder"

#: A pair imported together and analyzed apart, to find when rekordbox extracts
#: embedded cover art into share/PIONEER/Artwork. F4 already showed that an
#: import alone does not do it, but every track that did get artwork had been
#: analyzed and selected and displayed in the same session, so analysis was
#: never isolated from merely being looked at. Here F9 is analyzed and F10 is
#: left alone, so F10 controls for anything that follows from time passing or
#: from a background pass over the library. Both carry embedded art, and they
#: keep separate albums so neither can inherit the other's artwork.
TIMING_DIR = "rbe-artwork-timing"
TIMING = {
    "F9": (
        "/Volumes/GIG MUSIC/Contents/NxWorries (Anderson Paak & Knxwledge)/Yes Lawd!/19. Fkku.mp3",
        "RBE Remove Fixture Iota",
        "RBE Remove Fixture Artist Iota",
        "RBE Remove Fixture Album Iota",
    ),
    "F10": (
        "/Volumes/GIG MUSIC/Contents/Flying Lotus/Flamagra/22 - Pygmy.mp3",
        "RBE Remove Fixture Kappa",
        "RBE Remove Fixture Artist Kappa",
        "RBE Remove Fixture Album Kappa",
    ),
}


def build() -> int:
    missing = [label for label, spec in FIXTURES.items() if not Path(spec[0]).is_file()]
    if missing:
        for label in missing:
            print(f"  source missing for {label}: {FIXTURES[label][0]}", file=sys.stderr)
        return 1

    art_bytes = ID3(SHARED_ART_SOURCE).getall("APIC")[0].data

    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True)

    print(f"{'':4} {'file':44} artist / album")
    for label, (source, title, artist, album, genre) in FIXTURES.items():
        suffix = Path(source).suffix
        target = STAGING / f"{label.lower()}-{title.lower().replace(' ', '-')}{suffix}"
        shutil.copy2(source, target)

        tags = mutagen.File(target, easy=True)
        if tags is None:
            print(f"  cannot tag {target}", file=sys.stderr)
            return 1
        tags["title"] = title
        tags["artist"] = artist
        tags["album"] = album
        tags["genre"] = genre
        # Rekordbox reads albumartist separately; leaving it equal to the artist
        # keeps the album's AlbumArtistID pointed at a record the study owns.
        tags["albumartist"] = artist
        tags.save()

        if label in SHARED_ART or label in LABELS:
            tags = ID3(target)
            if label in SHARED_ART:
                tags.delall("APIC")
                tags.add(APIC(encoding=0, mime="image/jpeg", type=3,
                              desc="", data=art_bytes))
            if label in LABELS:
                tags.add(TPUB(encoding=3, text=LABELS[label]))
            tags.save()

        extra = ""
        if label in SHARED_ART:
            extra += "  [shared art]"
        if label in LABELS:
            extra += f"  [label: {LABELS[label]}]"
        print(f"{label:4} {target.name:44} {artist} / {album}{extra}")

    album_dir = STAGING / FOLDER_ART_DIR
    album_dir.mkdir()
    (album_dir / "cover.jpg").write_bytes(art_bytes)
    for fixture, (source, title) in FOLDER_ART.items():
        target = album_dir / f"{fixture.lower()}-{title.lower().replace(' ', '-')}.mp3"
        shutil.copy2(source, target)
        tags = mutagen.File(target, easy=True)
        tags["title"] = title
        tags["artist"] = FOLDER_ART_ARTIST
        tags["album"] = FOLDER_ART_ALBUM
        tags["albumartist"] = FOLDER_ART_ARTIST
        tags.save()
        stripped = ID3(target)
        stripped.delall("APIC")
        stripped.save()
        print(f"{fixture:4} {FOLDER_ART_DIR}/{target.name:29} "
              f"{FOLDER_ART_ARTIST} / {FOLDER_ART_ALBUM}  [folder art, no embedded]")

    timing_dir = STAGING / TIMING_DIR
    timing_dir.mkdir()
    for fixture, (source, title, artist, album) in TIMING.items():
        target = timing_dir / f"{fixture.lower()}-{title.lower().replace(' ', '-')}.mp3"
        shutil.copy2(source, target)
        tags = mutagen.File(target, easy=True)
        tags["title"] = title
        tags["artist"] = artist
        tags["album"] = album
        tags["albumartist"] = artist
        tags.save()
        embedded = len(ID3(target).getall("APIC")[0].data)
        print(f"{fixture:4} {TIMING_DIR}/{target.name:29} "
              f"{artist} / {album}  [embedded art {embedded}B]")

    print()
    print(f"staged {len(FIXTURES) + len(FOLDER_ART) + len(TIMING)} fixture(s) in {STAGING}")
    print("F1, F4: unique artist and album, so removal orphans them")
    print("F2, F3: share an artist and album with each other (the control)")
    print("F4:     import but do NOT analyze, to leave AnalysisDataPath empty")
    print("F5, F6: same album and byte-identical cover art; F5 alone has a label")
    print(f"F7, F8: in {FOLDER_ART_DIR}/ beside cover.jpg, embedded art stripped")
    print(f"F9, F10: in {TIMING_DIR}/, both with embedded art; analyze F9 ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
