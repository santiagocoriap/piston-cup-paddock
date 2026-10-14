"""Phase 5: the collector program from the GitHub releases, the update, and the zip."""

import hashlib
import io
import json
import zipfile

import pytest
from django.core.cache import cache
from django.test import Client

from apps.collectors import release

EXE = b"MZ fake program"
SUM = hashlib.sha256(EXE).hexdigest()
BASE = "https://github.com/x/y/releases/download"


def releases(version="1.2.0", sums=None):
    tag = f"collector-v{version}"
    return [
        {"tag_name": "collector-v9.9.9", "draft": True, "assets": []},
        {
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "paddock-collector.exe", "browser_download_url": f"{BASE}/{tag}/exe"},
                {"name": "SHA256SUMS", "browser_download_url": f"{BASE}/{tag}/sums"},
            ],
        },
        {"tag_name": "collector-v1.0.0", "draft": False, "assets": []},
        {"tag_name": "v3.0.0", "draft": False, "assets": []},
    ]


@pytest.fixture
def github(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.COLLECTOR_RELEASE_REPO = "x/y"
    cache.delete(release.CACHE_KEY)
    calls = []
    state = {"exe": EXE, "sums": f"{SUM}  paddock-collector.exe\n"}

    def fetch(url, limit):
        calls.append(url)
        if "api.github.com" in url:
            return json.dumps(releases()).encode()
        if url.endswith("/sums"):
            return state["sums"].encode()
        return state["exe"]

    monkeypatch.setattr(release, "_fetch", fetch)
    yield state, calls
    cache.delete(release.CACHE_KEY)


@pytest.fixture
def key(api, champ_admin, championship):
    response = api(champ_admin).post(f"/championships/{championship.id}/collectors", {"name": "AC"})
    return response.json()


def as_collector(raw, path):
    return Client().get(f"/api{path}", HTTP_AUTHORIZATION=f"Bearer {raw}")


def test_the_newest_release_with_a_program_and_a_sum(github):
    _state, calls = github
    found = release.latest()
    assert (found.version, found.sha256) == ("1.2.0", SUM)
    release.latest()
    assert len([c for c in calls if "api.github.com" in c]) == 1  # One time an hour.


def test_no_repository_means_no_release(github, settings):
    settings.COLLECTOR_RELEASE_REPO = ""
    assert release.latest() is None


def test_a_collector_asks_for_the_version_and_downloads_it(github, key):
    response = as_collector(key["key"], "/collector/version")
    assert response.json() == {"version": "1.2.0", "sha256": SUM}
    response = as_collector(key["key"], "/collector/download")
    assert response.content == EXE
    assert response["X-Paddock-Version"] == "1.2.0"
    assert as_collector("pcc_wrong", "/collector/version").status_code == 401


def test_a_program_with_a_wrong_sum_is_refused(github, key):
    state, _calls = github
    state["exe"] = b"MZ changed program"
    assert as_collector(key["key"], "/collector/download").status_code == 503


def test_the_admin_downloads_a_ready_zip(github, api, champ_admin, key):
    response = api(champ_admin).client.post(
        f"/api/collectors/{key['id']}/package",
        {"key": key["key"]},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert set(archive.namelist()) == {
        "paddock-collector.exe",
        "collector.ini",
        "instalar.bat",
        "desinstalar.bat",
        "LEEME.txt",
    }
    assert archive.read("paddock-collector.exe") == EXE
    ini = archive.read("collector.ini").decode()
    assert f"key = {key['key']}\r\n" in ini
    assert "url = http://testserver\r\n" in ini
    assert "results_dir =" in ini  # The rest of the example file stays.
    assert "--install" in archive.read("instalar.bat").decode()
    assert "realpenalty_exe =" in ini


def test_the_zip_needs_the_right_key(github, api, champ_admin, driver_user, key):
    url = f"/api/collectors/{key['id']}/package"
    wrong = api(champ_admin).client.post(url, {"key": "pcc_other"}, content_type="application/json")
    assert wrong.status_code == 422
    driver = api(driver_user).client.post(url, {"key": key["key"]}, content_type="application/json")
    assert driver.status_code in (403, 404)


def test_no_release_yet(github, api, champ_admin, key, settings):
    settings.COLLECTOR_RELEASE_REPO = ""
    response = api(champ_admin).client.post(
        f"/api/collectors/{key['id']}/package", {"key": key["key"]}, content_type="application/json"
    )
    assert response.status_code == 503
    assert as_collector(key["key"], "/collector/version").json() == {
        "version": None,
        "sha256": None,
    }
