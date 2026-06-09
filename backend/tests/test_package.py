import haruspex_server


def test_version_is_set() -> None:
    assert haruspex_server.__version__
