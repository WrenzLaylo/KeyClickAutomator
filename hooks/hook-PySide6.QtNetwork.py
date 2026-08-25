"""Use Windows' native TLS backend and omit unused OpenSSL/network plugins."""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)


def _needed(entry: tuple[str, str]) -> bool:
    source_name = Path(entry[0]).name.lower()
    destination = str(entry[1]).replace("\\", "/").lower()
    if source_name.startswith(("libcrypto-", "libssl-")):
        return False
    if "/plugins/" not in destination:
        return True
    return source_name == "qschannelbackend.dll"


binaries = [entry for entry in binaries if _needed(entry)]
