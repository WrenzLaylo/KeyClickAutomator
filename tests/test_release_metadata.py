import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
CONTROLLER = (ROOT / "qt_controller.py").read_text(encoding="utf-8")
INSTALLER = (ROOT / "installer.iss").read_text(encoding="utf-8")
VERSION_INFO = (ROOT / "version_info.txt").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_release_version_and_readme_stay_in_sync():
    match = re.search(r'^APP_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$', CONTROLLER, re.MULTILINE)
    assert match is not None
    version = match.group(1)

    assert f'#define MyAppVersion "{version}"' in INSTALLER
    assert f"OutputBaseFilename=KeyClickAutomator-Setup-{version}" in INSTALLER
    assert f"VersionInfoVersion={version}.0" in INSTALLER
    assert f"StringStruct(u'FileVersion', u'{version}')" in VERSION_INFO
    assert f"StringStruct(u'ProductVersion', u'{version}')" in VERSION_INFO

    assert f"> Current release: **{version}**" in README
    assert f"KeyClickAutomator-Portable-{version}.exe" in README
    assert f"KeyClickAutomator-Setup-{version}.exe" in README
    assert f"## What's new in {version}" in README
    assert f"| {version} |" in README


def test_packaged_builds_include_the_browser_control_dependency():
    """websocket-client is imported lazily, so PyInstaller cannot infer it."""
    for name in ("KeyClickAutomator.spec", "KeyClickAutomatorInstaller.spec"):
        spec = (ROOT / name).read_text(encoding="utf-8")
        assert "'websocket'" in spec, f"{name} would ship without browser control"
