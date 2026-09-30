import io
import json

import pytest

from r5ultra import updates


def test_versions_compare_as_numbers():
    assert updates.version_tuple("v1.10") == (1, 10)
    assert updates.is_newer("1.10", "1.9")
    assert updates.is_newer("v2.0", "1.8")
    assert not updates.is_newer("1.8", "1.8")
    assert not updates.is_newer("1.7", "1.8")
    assert not updates.is_newer("", "1.8")          # a release without a usable tag


def test_api_address_comes_from_the_repo():
    assert updates.API == "https://api.github.com/repos/Zelozzzz/R5-Ultra-Controller/releases/latest"
    assert updates.RELEASES == "https://api.github.com/repos/Zelozzzz/R5-Ultra-Controller/releases"


# a pretend github: what each address answers, and which ones got asked

def _github(monkeypatch, answers: dict):
    asked = []

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(request, timeout=0):
        url = request.full_url
        asked.append(url)
        if url not in answers:
            raise OSError(f"no such page: {url}")
        return Reply(json.dumps(answers[url]).encode())
    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    return asked


def _rel(tag, pre=False, draft=False):
    return {"tag_name": tag, "html_url": f"https://github.com/Zelozzzz/R5-Ultra-Controller/releases/tag/{tag}",
            "prerelease": pre, "draft": draft}


ALL = updates.RELEASES + "?per_page=10"


def test_someone_on_the_normal_release_only_hears_about_the_next_normal_one(monkeypatch):
    asked = _github(monkeypatch, {updates.API: _rel("v1.9"), ALL: [_rel("v1.11", pre=True), _rel("v1.9")]})
    found = updates.check(local="1.9")
    assert found == {"version": "1.9", "url": "https://github.com/Zelozzzz/R5-Ultra-Controller/releases/tag/v1.9",
                     "prerelease": False}
    assert asked == [updates.API]                    # pre-releases aren't even looked at
    asked.clear()
    assert updates.check(local="1.8")["version"] == "1.9" and asked == [updates.API]


def test_someone_on_a_pre_release_hears_about_the_next_pre_release(monkeypatch):
    asked = _github(monkeypatch, {updates.API: _rel("v1.9"),
                                  ALL: [_rel("v1.12", pre=True), _rel("v1.11", pre=True), _rel("v1.9"),
                                        _rel("v2.0", draft=True), _rel("nightly", pre=True)]})
    found = updates.check(local="1.11")
    assert found["version"] == "1.12" and found["prerelease"] and found["ahead"]
    assert found["url"].endswith("/releases/tag/v1.12")
    assert asked == [updates.API, ALL]               # drafts and tags without a number never win


def test_someone_on_the_newest_pre_release_is_told_so(monkeypatch):
    _github(monkeypatch, {updates.API: _rel("v1.9"), ALL: [_rel("v1.11", pre=True), _rel("v1.9")]})
    found = updates.check(local="1.11")
    assert found["version"] == "1.9" and found["ahead"] and not updates.is_newer(found["version"], "1.11")


def test_the_second_question_failing_keeps_the_first_answer(monkeypatch):
    _github(monkeypatch, {updates.API: _rel("v1.9")})          # /releases answers nothing
    found = updates.check(local="1.11")
    assert found["version"] == "1.9" and found["ahead"]


def test_the_first_question_failing_is_still_an_error(monkeypatch):
    _github(monkeypatch, {})
    with pytest.raises(OSError):
        updates.check(local="1.11")
