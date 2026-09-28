"""Asks github if there's a newer release."""

from __future__ import annotations

import json
import re
import urllib.request

from . import REPO_URL, __version__

API = REPO_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text or ""))


def is_newer(remote: str, local: str = __version__) -> bool:
    return bool(version_tuple(remote)) and version_tuple(remote) > version_tuple(local)


def latest(timeout: float = 6.0) -> dict:
    request = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                  "User-Agent": f"Dorsal/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    return {"version": str(data.get("tag_name", "")).lstrip("v"),
            "url": data.get("html_url") or f"{REPO_URL}/releases/latest"}
