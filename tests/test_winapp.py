from dorsal import winapp


def test_normal_settings_folder_keeps_the_installer_names():
    env = {"APPDATA": r"C:\Users\Sam\AppData\Roaming", "USERPROFILE": r"C:\Users\Sam"}
    assert winapp.instance_names(env) == (winapp.MUTEX_NAME, winapp.SHOW_EVENT)


def test_other_settings_folders_get_their_own_names():
    # A test run (or second setup) must never answer the normal copy's launches.
    normal = {"APPDATA": r"C:\Users\Sam\AppData\Roaming", "USERPROFILE": r"C:\Users\Sam"}
    test_a = dict(normal, APPDATA=r"C:\Temp\run-a")
    test_b = dict(normal, APPDATA=r"C:\Temp\run-b")
    names = {winapp.instance_names(e) for e in (normal, test_a, test_b)}
    assert len(names) == 3
    assert winapp.instance_names(test_a) == winapp.instance_names(dict(test_a))
