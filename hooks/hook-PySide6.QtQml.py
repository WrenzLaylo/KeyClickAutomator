"""Collect only the QML modules used by KeyClick Automator.

PyInstaller's stock QtQml hook intentionally collects every installed QML
module. The PySide6 wheel includes large optional families such as WebEngine,
3D, Charts, Multimedia, and PDF, none of which this application imports.
"""

from pathlib import Path, PurePath

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

# QML debugging plugins are development tools. One of them also pulls the
# otherwise unused Qt Quick 3D utility library into the release.
binaries = [
    entry for entry in binaries
    if "/plugins/qmltooling" not in str(entry[1]).replace("\\", "/").lower()
]

_QML_MODULES = (
    "QtQml",
    "QtQml/Models",
    "QtQml/WorkerScript",
    "QtQuick",
    "QtQuick/Window",
    "QtQuick/Layouts",
    "QtQuick/Effects",
    "QtQuick/Shapes",
    "QtQuick/Templates",
    "QtQuick/Controls",
    "QtQuick/Controls/impl",
    "QtQuick/Controls/Basic",
    "QtQuick/Controls/Basic/impl",
    "Qt/labs/qmlmodels",
)

qml_source = Path(pyside6_library_info.location["QmlImportsPath"]).resolve()
qml_destination = PurePath(pyside6_library_info.qt_rel_dir) / "qml"

for module in _QML_MODULES:
    module_path = qml_source / module
    plugin_binaries, plugin_datas = pyside6_library_info._process_qml_plugin(module_path / "qmldir")
    destination = qml_destination / PurePath(module)
    binaries += [(str(path), str(destination)) for path in plugin_binaries]
    datas += [(str(path), str(destination)) for path in plugin_datas]
