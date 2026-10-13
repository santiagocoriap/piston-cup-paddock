"""Pack track maps, track pictures and car pictures from Assetto Corsa into one ZIP.

Run it on a PC with the game. Then upload the ZIP in the app: Admin > Pistas y autos.

    python pack_game_images.py --needed paddock-needed.json

--needed is the list that the app gives ("Descargar lista"). Without it, the script packs
every track and car of the game, which can be a large file.
--game is the assettocorsa folder. Without it, the script looks in the usual Steam folders.

Standard library only: it needs Python 3.10 or later and nothing else.
"""

import argparse
import json
import string
import sys
import zipfile
from pathlib import Path

TRACK_FILES = ("outline.png", "preview.png", "ui_track.json")
CAR_FILES = ("badge.png", "ui_car.json")
STEAM_SUFFIX = Path("steamapps") / "common" / "assettocorsa"


def find_game() -> Path | None:
    candidates = [Path("C:/Program Files (x86)/Steam") / STEAM_SUFFIX]
    for drive in string.ascii_uppercase:
        candidates.append(Path(f"{drive}:/SteamLibrary") / STEAM_SUFFIX)
        candidates.append(Path(f"{drive}:/Steam") / STEAM_SUFFIX)
    candidates.append(Path.home() / ".steam" / "steam" / STEAM_SUFFIX)
    return next((c for c in candidates if (c / "content" / "tracks").is_dir()), None)


def child(folder: Path, name: str) -> Path | None:
    """A file or folder by name, without case: the result file and the folder can differ."""
    exact = folder / name
    if exact.exists():
        return exact
    if not folder.is_dir():
        return None
    return next((c for c in folder.iterdir() if c.name.lower() == name.lower()), None)


def pack(content: Path, needed: dict | None, out: Path) -> tuple[int, int, list[str]]:
    tracks_dir, cars_dir = content / "tracks", content / "cars"
    if needed is None:
        tracks = []
        for track in sorted(p for p in tracks_dir.iterdir() if (p / "ui").is_dir()):
            layouts = [p.name for p in (track / "ui").iterdir() if p.is_dir()]
            tracks += [{"track": track.name, "layout": layout} for layout in layouts] or [
                {"track": track.name, "layout": ""}
            ]
        cars = sorted(p.name for p in cars_dir.iterdir() if p.is_dir())
    else:
        tracks, cars = needed.get("tracks", []), needed.get("cars", [])

    missing, track_count, car_count = [], 0, 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in tracks:
            track = child(tracks_dir, item["track"])
            ui = child(track, "ui") if track else None
            folder = child(ui, item["layout"]) if ui and item["layout"] else ui
            if folder is None:
                missing.append(f"track {item['track']} {item['layout']}".strip())
                continue
            base = f"tracks/{item['track']}/ui" + (f"/{item['layout']}" if item["layout"] else "")
            for name in TRACK_FILES:
                path = child(folder, name)
                if path and path.is_file():
                    archive.write(path, f"{base}/{name}")
            track_count += 1
        for key in cars:
            car = child(cars_dir, key)
            if car is None:
                missing.append(f"car {key}")
                continue
            ui = child(car, "ui")
            for name in CAR_FILES:
                path = child(ui, name) if ui else None
                if path and path.is_file():
                    archive.write(path, f"cars/{key}/ui/{name}")
            skins = child(car, "skins")
            previews = sorted(p / "preview.jpg" for p in skins.iterdir()) if skins else []
            preview = next((p for p in previews if p.is_file()), None)
            if preview:
                archive.write(preview, f"cars/{key}/preview.jpg")
            car_count += 1
    return track_count, car_count, missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--game", type=Path, help="The assettocorsa folder.")
    parser.add_argument("--needed", type=Path, help="The list from the app (paddock-needed.json).")
    parser.add_argument(
        "--out", type=Path, default=Path("paddock-images.zip"), help="The ZIP to write."
    )
    args = parser.parse_args()

    game = args.game or find_game()
    if game is None:
        print("Assetto Corsa was not found. Give the folder with --game.", file=sys.stderr)
        return 1
    content = game / "content" if (game / "content").is_dir() else game
    if not (content / "tracks").is_dir():
        print(f"{content} has no tracks folder.", file=sys.stderr)
        return 1
    needed = json.loads(args.needed.read_text(encoding="utf-8")) if args.needed else None

    tracks, cars, missing = pack(content, needed, args.out)
    size = args.out.stat().st_size / 1024 / 1024
    print(f"Wrote {args.out} ({size:.1f} MB): {tracks} layouts, {cars} cars.")
    for item in missing:
        print(f"  Not in the game folder: {item}")
    print("Next: upload the ZIP in the app, Admin > Pistas y autos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
