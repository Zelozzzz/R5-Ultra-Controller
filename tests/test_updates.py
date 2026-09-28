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
