<p align="center">
  <img src="assets/app-logo-transparent.png" alt="KeyClick Automator logo" width="88">
</p>

<h1 align="center">KeyClick Automator</h1>

<p align="center">
  Build keyboard and mouse automation as a clear, visual sequence.<br>
  Made for Windows with Python, PySide6, and Qt Quick.
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#controls-and-safety">Controls</a> ·
  <a href="#run-from-source">Run from source</a> ·
  <a href="#build-a-release">Build a release</a>
</p>

> Current release: **3.0.8** · Windows 10/11 · 64-bit

## Why KeyClick

KeyClick turns repetitive input into an ordered workflow you can inspect before
running. Add steps, adjust timing, temporarily switch steps off, save the result,
and stop the automation immediately whenever you need to.

- Keyboard presses, shortcuts, and typed text
- Left, right, double, and middle mouse clicks
- Scrolling and pointer dragging
- Per-action repeats and delays
- Finite runs or continuous looping
- Saveable `.kca.json` profiles
- Responsive desktop layout with a slide-over inspector
- Global shortcuts and a corner fail-safe

## Choose a build

| Build | Best for | What you need |
| --- | --- | --- |
| `KeyClickAutomator-Portable-3.0.8.exe` | Carrying the app on a USB drive or running it without installation | Just the one `.exe`; Python and Qt are already bundled |
| `KeyClickAutomator-Setup-3.0.8.exe` | A normal Windows installation with shortcuts and uninstall support | Run the installer once; it installs everything the app needs |

Both builds are created in the `release` folder. The portable build is one
standalone file. The setup download is smaller because it installs the bundled
runtime as a normal application folder.

> The builds are currently unsigned, so Windows SmartScreen may show a warning.
> Only run a file you built yourself or downloaded from a release you trust.

## Quick start

1. Open KeyClick Automator.
2. Select **Create first action** or **New action**.
3. Choose an action type, enter its details, and select **Add to sequence**.
4. Add more actions in the order they should run.
5. Select a sequence card to edit it. Use its switch to skip or restore that step.
6. Select **Start** or press `F6`.
7. Press `F9` at any time for an emergency stop.

Example sequence:

| Step | Action | Timing |
| ---: | --- | --- |
| 01 | Press `ENTER` | Wait 0.1 seconds |
| 02 | Type `Hello` | Wait 0.2 seconds |
| 03 | Left click at the saved pointer position | Wait 0.5 seconds |

Disabled steps stay in the sequence but are skipped during a run. Their toggle
and content animate smoothly, and the toggle always remains available so the
step can be turned back on.

## Supported actions

| Category | Actions |
| --- | --- |
| Keyboard | Key press, multi-key shortcut, type text |
| Pointer | Left click, right click, double click, middle click |
| Movement | Scroll, drag pointer |

Every action can be edited, enabled or disabled, repeated, delayed, reordered,
duplicated, and deleted.

## Controls and safety

| Default key | Action |
| --- | --- |
| `F6` | Start or toggle the current run |
| `F8` | Capture the current pointer position |
| `F9` | Stop immediately |

The shortcuts can be recorded and changed in the **Run** inspector. On laptops,
you may need to hold `Fn` to send an F-key. KeyClick also keeps PyAutoGUI's corner
fail-safe active: moving the pointer into a screen corner can stop automation.

Before a long or repeating run, test the sequence with a small cycle count and
make sure `F9` works with your keyboard.

## Profiles

- **Save profile** stores the sequence and run settings in a `.kca.json` file.
- **Open profile** restores a saved sequence.
- Profiles remain compatible with the 3.x interface.

## What's new in 3.0.8

- Redesigned sequence cards as a numbered blue workflow
- Smooth, interruptible on/off animation for each action
- Action switches remain usable after a step is disabled
- Cleaner hover, pressed, and editing states without dark flashes
- Correctly aligned action-type dropdown
- Compact, fixed-size F-key shortcut dock
- Better balanced Start and Stop controls
- Smaller portable and setup packages
- Transparent app logo with a cleaner navigation rail

## Release history

| Version | Summary |
| --- | --- |
| 3.0.8 | Workflow-card redesign, compact controls, packaging reduction, and animated action toggles |
| 3.0.7 | Neutral navigation hover treatment |
| 3.0.6 | Safe recording for all global shortcuts |
| 3.0.2 | Runtime-driven version labels |
| 3.0.1 | Repaired interaction states and sequence visibility |
| 3.0.0 | Complete Qt Quick interface rebuild |
| 2.1.0 | Previous modern desktop release |

The release process is documented in [RELEASING.md](RELEASING.md). Its checklist
requires every version bump to update this README, and the automated tests verify
that the current version, artifact names, and release notes stay in sync.

## Run from source

Requirements: Windows and Python 3. Git is only needed if you clone the repository.

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe qt_app.py
```

No installation step is needed after the dependencies finish installing.

## Run the tests

```powershell
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest -q
```

The suite covers the automation engine, cancellation and timing, profile files,
controller behavior, responsive breakpoints, QML loading, interaction states,
and release-version consistency.

## Build a release

Build the single-file portable app:

```powershell
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm KeyClickAutomator.spec
New-Item -ItemType Directory -Force release | Out-Null
Copy-Item dist\KeyClickAutomator.exe release\KeyClickAutomator-Portable-3.0.8.exe
```

Build the installer payload, then compile it with Inno Setup 6:

```powershell
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm KeyClickAutomatorInstaller.spec
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "installer.iss"
```

Close any running release copy before rebuilding, and adjust the `ISCC.exe` path
if Inno Setup was installed somewhere else.

Before publishing, complete every check in [RELEASING.md](RELEASING.md).

## Project layout

| Path | Purpose |
| --- | --- |
| `qml/Main.qml` | Desktop interface and animations |
| `qt_controller.py` | UI model, profile actions, and run coordination |
| `engine.py` | Automation actions, validation, timing, and execution |
| `tests/` | Controller, engine, QML, responsive, and release tests |
| `KeyClickAutomator.spec` | Single-file portable build |
| `KeyClickAutomatorInstaller.spec` | Multi-file installer payload |
| `installer.iss` | Inno Setup configuration |

## Font license

Inter is distributed under the SIL Open Font License 1.1. The full license is
included at `assets/fonts/LICENSE.txt` and packaged with the application.
