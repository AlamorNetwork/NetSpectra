"""Verify the installed distribution exposes the expected package version."""

from importlib.metadata import version

import pprl_core


def test_installed_version_matches_package() -> None:
    assert pprl_core.__version__ == version("pprl")
