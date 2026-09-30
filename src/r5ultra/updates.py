"""Asks github if there's a newer release.

The update check asks for the release everyone gets (releases/latest, pre-releases don't count there). A copy
that's already ahead of that is a pre-release, and for it the newest pre-release counts too, so people trying
one hear about the next.
"""

from __future__ import annotations

import json
import re
import urllib.request

from . import REPO_URL, __version__

RELEASES = REPO_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases"
API = RELEASES + "/latest"


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text or ""))


def is_newer(remote: str, local: str = __version__) -> bool:
    return bool(version_tuple(remote)) and version_tuple(remote) > version_tuple(local)


def _get(url: str, timeout: float):
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                  "User-Agent": f"Dorsal/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _release(data: dict) -> dict:
    return {"version": str(data.get("tag_name", "")).lstrip("v"),
            "url": data.get("html_url") or f"{REPO_URL}/releases/latest",
            "prerelease": bool(data.get("prerelease"))}


def latest(timeout: float = 6.0) -> dict:
    """The release everyone gets."""
    return _release(_get(API, timeout))


def newest(timeout: float = 6.0) -> dict | None:
    """The newest release by version number, pre-releases included (drafts never). None if there's nothing with
    a version number in its tag."""
    releases = [r for r in _get(RELEASES + "?per_page=10", timeout)
                if not r.get("draft") and version_tuple(str(r.get("tag_name", "")))]
    if not releases:
        return None
    return _release(max(releases, key=lambda r: version_tuple(str(r.get("tag_name", "")))))


def check(timeout: float = 6.0, local: str = __version__) -> dict:
    """What Dorsal shows. The release everyone gets, unless this copy is ahead of it (a pre-release): then it's
    the newest pre-release if there's a newer one, and "ahead" says this copy is past the normal release."""
    found = latest(timeout)
    if found["version"] and is_newer(local, found["version"]):
        found["ahead"] = True
        try:
            ahead = newest(timeout)
        except Exception:                              # the second question failing doesn't lose the first answer
            ahead = None
        if ahead and is_newer(ahead["version"], local):
            return {**ahead, "ahead": True}
    return found
