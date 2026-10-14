"""The server collector program for Windows (phase 5 of docs/plans/ac-integration.md).

GitHub Actions builds `paddock-collector.exe` for each `collector-v*` tag of the repository
(.github/workflows/collector.yml). The release has the program and a SHA256SUMS file. The app
finds the newest release, keeps a copy of the program in the media folder, and gives it to:

- an admin, in a zip with a ready collector.ini ("Descargar colector").
- the collectors, which ask for the newest version one time a day and update themselves.

The collectors download the program from the app only, with their key. They never go to GitHub.
"""

import hashlib
import io
import json
import re
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

EXE_NAME = "paddock-collector.exe"
TAG = re.compile(r"^collector-v(\d+\.\d+\.\d+)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CACHE_KEY = "collector-release"
CACHE_SECONDS = 3600
MAX_EXE_BYTES = 80 * 1024 * 1024


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    sha256: str
    exe_url: str


def _fetch(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "piston-cup-paddock"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (https only)
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ReleaseError("too_big")
    return data


def _sha_of(sums: str, name: str) -> str | None:
    """The sum of one file in a SHA256SUMS text: "<sum>  <name>" on each line."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and SHA256.match(parts[0].lower()):
            return parts[0].lower()
    return None


def _find() -> Release | None:
    repo = settings.COLLECTOR_RELEASE_REPO
    if not repo:
        return None
    url = f"https://api.github.com/repos/{repo}/releases?per_page=30"
    releases = json.loads(_fetch(url, 2 * 1024 * 1024))
    found = []
    for item in releases:
        match = TAG.match(item.get("tag_name") or "")
        if not match or item.get("draft") or item.get("prerelease"):
            continue
        assets = {a["name"]: a["browser_download_url"] for a in item.get("assets", [])}
        if EXE_NAME in assets and "SHA256SUMS" in assets:
            found.append((tuple(int(n) for n in match[1].split(".")), match[1], assets))
    if not found:
        return None
    _number, version, assets = max(found)
    sha = _sha_of(_fetch(assets["SHA256SUMS"], 64 * 1024).decode(), EXE_NAME)
    if sha is None:
        raise ReleaseError("no_sum")
    return Release(version=version, sha256=sha, exe_url=assets[EXE_NAME])


def latest() -> Release | None:
    """The newest collector release. The app asks GitHub one time an hour at most."""
    found = cache.get(CACHE_KEY)
    if found is None:
        try:
            release = _find()
        except (OSError, ValueError, KeyError, ReleaseError):
            # GitHub is not available. Ask again in 5 minutes, not on each request.
            cache.set(CACHE_KEY, {"release": None}, 300)
            return None
        found = {"release": release}
        cache.set(CACHE_KEY, found, CACHE_SECONDS)
    return found["release"]


def program(release: Release) -> bytes:
    """The program of a release. The app downloads it one time and keeps a copy."""
    folder = Path(settings.MEDIA_ROOT) / "collector"
    path = folder / f"paddock-collector-{release.version}.exe"
    if path.exists():
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() == release.sha256:
            return data
    data = _fetch(release.exe_url, MAX_EXE_BYTES)
    if hashlib.sha256(data).hexdigest() != release.sha256:
        raise ReleaseError("bad_sum")
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def collector_ini(app_url: str, key: str) -> str:
    """collector.ini for a new collector: the example file with the app address and the key."""
    text = Path(settings.COLLECTOR_INI_TEMPLATE).read_text(encoding="utf-8")
    text = re.sub(r"(?m)^url = .*$", lambda _m: f"url = {app_url}", text, count=1)
    text = re.sub(r"(?m)^key = .*$", lambda _m: f"key = {key}", text, count=1)
    return text.replace("; Copy this file to collector.ini and change the values.", _INI_HEAD, 1)


_INI_HEAD = (
    "; Made by the app for this collector. The key is secret.\n"
    "; Write the folders of your AC server below, then run instalar.bat."
)

INSTALL_BAT = r"""@echo off
rem Puts the shortcut "Iniciar Paddock" on the desktop. It starts Real Penalty and the collector.
cd /d "%~dp0"
paddock-collector.exe --install --config "%~dp0collector.ini"
"""

UNINSTALL_BAT = r"""@echo off
rem Removes the shortcut "Iniciar Paddock" from the desktop.
cd /d "%~dp0"
paddock-collector.exe --uninstall
"""

README = """Piston Cup Paddock - colector del servidor

1. Copiá esta carpeta a la PC del servidor de AC, por ejemplo C:\\PaddockCollector.
2. Abrí collector.ini con el Bloc de notas. Escribí las carpetas del servidor y la ruta de
   ac_penalty.exe (realpenalty_exe) en [server].
3. Hacé doble clic en instalar.bat. Aparece "Iniciar Paddock" en el escritorio.
4. Windows puede mostrar "Windows protegió su PC". Hacé clic en "Más información" y después en
   "Ejecutar de todas formas". El programa no tiene firma de código.

Antes de cada carrera, abrí "Iniciar Paddock" en lugar de Real Penalty. Abre Real Penalty y el
colector. El colector no tiene ventana. Se cierra solo 15 minutos después de que el servidor se
apaga, cuando ya mandó todo. No arranca con Windows.
Al arrancar, el colector se actualiza solo si hay una versión nueva.
El registro está en collector.log, en esta carpeta.
Para sacar el acceso directo: doble clic en desinstalar.bat.
"""


def package(release: Release, app_url: str, key: str) -> bytes:
    """The zip for "Descargar colector"."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(EXE_NAME, program(release))
        files = {
            "collector.ini": collector_ini(app_url, key),
            "instalar.bat": INSTALL_BAT,
            "desinstalar.bat": UNINSTALL_BAT,
            "LEEME.txt": README,
        }
        for name, text in files.items():
            archive.writestr(name, text.replace("\r\n", "\n").replace("\n", "\r\n"))
    return buffer.getvalue()
