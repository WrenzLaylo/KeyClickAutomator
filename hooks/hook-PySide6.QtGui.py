"""Keep only the Windows and ICO plugins used by the application."""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

_RELEASE_PLUGINS = {"qico.dll", "qwindows.dll"}


def _needed(entry: tuple[str, str]) -> bool:
    destination = str(entry[1]).replace("\\", "/").lower()
    if "/plugins/" not in destination:
        return True
    return Path(entry[0]).name.lower() in _RELEASE_PLUGINS


binaries = [entry for entry in binaries if _needed(entry)]
