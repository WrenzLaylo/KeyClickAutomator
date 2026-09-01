<p align="center">
  <img src="assets/app-logo-transparent.png" alt="KeyClick Automator logo" width="88">
</p>

<h1 align="center">KeyClick Automator</h1>

<p align="center">
  <a href="https://github.com/WrenzLaylo/KeyClickAutomator/actions/workflows/windows-ci.yml"><img src="https://github.com/WrenzLaylo/KeyClickAutomator/actions/workflows/windows-ci.yml/badge.svg" alt="Windows CI status"></a>
  <a href="https://github.com/WrenzLaylo/KeyClickAutomator/releases/latest"><img src="https://img.shields.io/github/v/release/WrenzLaylo/KeyClickAutomator" alt="Latest GitHub release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/WrenzLaylo/KeyClickAutomator" alt="MIT License"></a>
</p>

<p align="center">
  Build keyboard and mouse automation as a clear, visual sequence.<br>
  Made for Windows with Python, PySide6, and Qt Quick.
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#profiles">Profiles</a> ·
  <a href="#controls-and-safety">Controls</a> ·
  <a href="#run-from-source">Run from source</a> ·
  <a href="#build-a-release">Build a release</a>
</p>

> Current release: **3.5.0** · Windows 10/11 · 64-bit

<p align="center">
  <img src="assets/screenshots/keyclick-main.png" alt="KeyClick Automator showing a visual sequence and the Run inspector" width="1200">
</p>

## Why KeyClick

KeyClick turns repetitive input into an ordered workflow you can inspect before
running. Add steps, adjust timing, temporarily switch steps off, save the result,
and stop the automation immediately whenever you need to.

- Keyboard presses, shortcuts, and typed text
- Left, right, double, and middle mouse clicks
- Click at a saved position or wherever the pointer is currently moving
- Send actions to one background window while your physical mouse stays free
- Drive a single Chrome tab, even while it is hidden or its window is minimised
- Pick your computer, an open window, or a browser tab from one list
- Refuses to start a run that cannot work, and says what to fix
- Record precise points on a frozen, dimmed copy of the screen
- Keep window-relative pointer positions aligned when the target is resized
- Scrolling and pointer dragging
- Per-action repeats and delays
- Finite runs or continuous looping
- Saveable `.kca.json` profiles
- Sequential or guarded parallel runs for several saved profiles
- Sequence, Profiles, and Runner as top-level tabs, with a docked Run inspector
- Global shortcuts and a corner fail-safe

## Choose a build

| Build | Best for | What you need |
| --- | --- | --- |
| `KeyClickAutomator-Portable-3.5.0.exe` | Carrying the app on a USB drive or running it without installation | Just the one `.exe`; Python and Qt are already bundled |
| `KeyClickAutomator-Setup-3.5.0.exe` | A normal Windows installation with shortcuts and uninstall support | Run the installer once; it installs everything the app needs |

Both builds are created in the `release` folder. The portable build is one
standalone file. The setup download is smaller because it installs the bundled
runtime as a normal application folder.

> The builds are currently unsigned, so Windows SmartScreen may show a warning.
> Only run a file you built yourself or downloaded from a release you trust.

Each GitHub release includes `SHA256SUMS.txt`. Use it to verify that a downloaded
portable app or installer exactly matches the file published with that release.

## Quick start

1. Open KeyClick Automator.
2. Open the **Profiles** tab or press `Ctrl+O` to switch to a saved sequence without
   leaving KeyClick. To start fresh, select **Create first action** or **New action**.
3. In the **Run** inspector, select **Change what it automates**. One list shows
   this computer, every open window, and every tab in KeyClick's automation
   browser. Pick the thing you want automated; KeyClick works out how to reach it.
4. Choose an action type and enter its details.
5. For a fixed mouse target, select **Pick pointer position**. KeyClick hides,
   freezes, and dims the current desktop; click the exact point without rushing,
   or press `Esc` to cancel. For clicks that should follow your hand, enable
   **Follow current pointer** instead in Desktop mode.
6. Select **Add to sequence**, then add more actions in the order they should run.
7. Drag a card by its six-dot grip to reorder it; the numbered timeline stays in
   place while only the card follows the pointer. You can also use **Up** or
   **Down**. Select any card to edit, test, duplicate, or disable it.
8. Select **Start**. Any visible Run changes are validated and applied first.
9. Press `F9` at any time for an emergency stop.

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

Every action can be edited, enabled or disabled, repeated, delayed, reordered by
dragging its grip or using **Up**/**Down**, duplicated, and deleted.

### Click while moving the pointer

For **Left click**, **Right click**, **Double click**, or **Middle click**, enable
**Follow current pointer**. KeyClick then clicks wherever the pointer is at that
moment and does not move it to saved coordinates, so you can keep moving the
mouse while repeated clicks run. Leave the option off when every click must land
at one fixed screen position.

Scroll and drag actions continue to use recorded positions because those actions
need a defined target or path.

### Automate one window in the background

Choose an open window from the target picker. Each entry shows a live preview,
so you can tell two windows of the same app apart. Use **Refresh** after opening
or restoring another app.

Record mouse positions again in this mode so they are saved relative to that
window instead of the desktop. KeyClick also records the window's content size.
When the target is resized later, each click, scroll point, and drag endpoint is
scaled to the new size before the action is delivered.

While the sequence runs, KeyClick sends keyboard and mouse messages only to the
selected window. It can stay behind other windows and your physical pointer does
not move, so you can keep using the mouse elsewhere. Keep the target open,
restored, and at the same privilege level as KeyClick.

Background delivery works best with standard Windows controls. KeyClick paces
every message, checks that the target is still responsive, splits large text
inserts, and sends wheel actions as individual notches so a fast sequence cannot
flood the target's Windows message queue. Some games, raw-input applications,
elevated programs, and modern or custom-rendered controls may still ignore or
reject message-based input. Use **Test once** before a repeating run. If the
target becomes unstable or closes, do not retry it in background mode; switch to
**Desktop** mode instead. KeyClick blocks desktop-relative actions from running
in window mode (and vice versa) until their positions are recorded again.

### Automate one browser tab

Web pages cannot be automated as background windows. A browser draws the page
itself and leaves no window underneath it to receive a click, so those clicks
arrive nowhere while appearing to succeed. KeyClick refuses that combination and
points you here instead.

Select **Change what it automates**, then **Start browser**. KeyClick opens Chrome
in its own profile, separate from your everyday windows — Chrome does not allow
automation of your normal profile. Open the page you want, refresh the list, and
pick its tab.

Positions are recorded by clicking in the page itself, so there is no screen
arithmetic to get wrong, and they follow the page when the window is resized.
While the sequence runs, input goes to that one tab: your pointer stays free,
every other tab, window, and Chrome profile is untouched, and it keeps working
while the tab sits behind another tab and its window is minimised.

After a run KeyClick reports what the page actually received, for example
`240 confirmed on button#bigCookie`. If it reports that the page received none
of them, the recorded position is no longer over the element you meant.

Pages usually ignore input sent faster than they can process. A short wait
between clicks often delivers more of them than no wait at all.

## Controls and safety

| Default key | Action |
| --- | --- |
| `F6` | Start or toggle the current run |
| `F8` | Open the frozen-screen pointer picker |
| `F9` | Stop immediately |

The shortcuts can be recorded and changed in the **Run** inspector. On laptops,
you may need to hold `Fn` to send an F-key. In Desktop mode, KeyClick also keeps
PyAutoGUI's corner fail-safe active: moving the pointer into a screen corner can
stop automation. Background window mode leaves the physical pointer untouched;
use `F9` to stop it.

Use **Test once** to try the selected step after a three-second safety countdown,
or **Run from here** to start at the selected step. The active sequence card is
highlighted while automation runs. Before a long or repeating run, make sure
`F9` works with your keyboard.

## Profiles

- The **Profiles** tab (`Ctrl+O`) is an in-app library of `.kca.json` profiles in the
  current profile folder. Select any row to switch sequences immediately.
- The portable build starts with the folder beside its `.exe`, so profiles saved
  beside KeyClick appear automatically. **Change** can point the library elsewhere.
- Each row shows its action count and modified time; the loaded profile is marked
  **Current**, and unreadable KeyClick files are clearly unavailable.
- Unsaved edits still trigger **Save**, **Discard**, or **Cancel** before switching.
- `Ctrl+S` saves directly to the active profile. Use `Ctrl+Shift+S` or **Save as…**
  to create another profile, which also becomes the library's current folder.
- **Open file…** can load a profile from another folder; the library then follows
  that folder and lists its other profiles.
- Select **Queue** beside any saved profile, then open the **Runner** tab to reorder
  the profiles, watch each profile's status and progress, or remove it before starting.
- The Multi-Profile Runner reloads each saved copy without replacing the sequence
  open in the editor. **Sequential** runs one profile after another; a profile
  that loops indefinitely must be last.
- **Parallel** runs two to eight profiles together only when they target different
  background windows. Desktop profiles, duplicate target windows, and actions that
  conflict with the runner's global safety shortcuts are blocked before input starts.
- Active run cards provide **Pause**, **Resume**, and **Stop**. In Parallel mode,
  stopping one profile does not stop the others. **Stop all** or `F9` stops every
  active profile and cancels anything still waiting.
- The selected target mode, window identity, coordinate type, and responsive
  window-size references are saved too.
- Unsaved edits are protected by a confirmation dialog and an automatic recovery
  copy if the app or computer closes unexpectedly.
- A deleted action can be restored with **Undo** or `Ctrl+Z`.
- Profiles created by earlier 3.x releases remain compatible.

## What's new in 3.5.0

- **Browser tab automation**: target one Chrome tab and drive only that tab.
  Your pointer stays free, other Chrome windows and profiles are untouched, and
  it keeps working while the tab is hidden behind another tab and its window is
  minimised. Background-window mode never could click a web page: browsers draw
  page content themselves and leave no window under it to receive a click
- **One target picker**: choose your computer, an open window, or a browser tab
  from a single list, and KeyClick works out how to reach it. A browser window is
  still listed, but tells you to pick that app's tab instead, and why
- **Checks before every run**: Start refuses a sequence that cannot work and says
  what to fix — a click whose position was never recorded, positions recorded for
  a different target, an unreachable window or a closed tab
- **Honest run reports**: a browser run confirms what the page actually received,
  so it reads `240 confirmed on button#bigCookie` rather than only "Complete"
- **Earlier versions of every profile**: each save and delete keeps a copy first,
  and any profile row can restore one. Restoring is itself undoable
- **Multi-Profile Runner**: queue saved profiles and run them one after another,
  or run up to eight background-window or browser-tab profiles together, with
  per-profile pause, resume, and stop
- **Tabbed navigation**: Sequence, Profiles, and Runner are top-level tabs rather
  than side drawers, so nothing slides over the sequence you are editing
- Saved profiles can be deleted from the Profiles page, with confirmation
- Window targets survive a changing title bar, so a page that writes live data
  into its title stays matched instead of becoming ambiguous
- A run reports its step and progress even when the Runner is set to Parallel
- A **Follow current pointer** click no longer has to be recorded again after the
  target changes, because it has no saved position to correct
- Buttons no longer separate from their label when pressed, hovering a tab no
  longer flashes dark, and hover tooltips that only repeated a button's own label
  are gone
- Long status messages wrap inside the toast instead of spilling past its edges

### Previous release: 3.4.4

- Modified hotkeys now record the intended printable key on Windows, including
  `Ctrl+Shift+C` and `Ctrl+Alt+C`, instead of displaying a control character or
  raw virtual-key value
- Shared buttons now center their complete icon, label, and shortcut-hint group;
  recovery, profile, and window-picker actions also use compact consistent widths
- The sequence status stays pinned to the far right while long profile summaries
  elide cleanly, and profile footer actions no longer stretch across the drawer
- Dragging a sequence moves only its card surface while numbered badges and the
  vertical timeline remain anchored, with the final order settling immediately
- Window-picker scrollbar spacing now stays inside the rounded dialog even after
  fast scrolling, while its Close label remains centered

### Earlier release: 3.4.3

- Scrollbars now appear only when content overflows, and long sequence and profile
  lists reserve a clear gutter so cards never sit beneath the scroll thumb
- The window picker stays bounded during fast scrolling and keeps its content,
  Refresh action, and Close action stable and visible
- Profile controls, the Ready badge, and the unsaved-changes dialog now use a
  cleaner, more consistent button hierarchy and alignment
- Changing action type or selection cancels an active key recording immediately,
  so pointer recording is never blocked by a stale listener
- Hotkey actions now include a dedicated recorder that waits for a modifier-plus-key
  combination, and card dragging keeps the numbered timeline anchored until drop

### Earlier release: 3.4.2

- Custom global shortcuts now reserve the complete chord instead of every
  individual key, so a Start shortcut such as `Ctrl+S` no longer blocks an
  unrelated `Ctrl+C` action
- Key and Hotkey actions reject mismatched input before the countdown begins,
  and duplicate global shortcuts are highlighted directly in Run settings
- The compact Run controls keep their shortcut hints contained, the inspector
  scrollbar has a clear form gutter, and shared UI/controller services are now
  split into safer reusable components
- Windows CI, an actual application screenshot, MIT licensing, and downloadable
  SHA-256 manifests make source and release verification easier

### Earlier release: 3.4.1

- Background messages are rate-limited and the target is checked for responsiveness
  throughout a run, preventing zero-delay sequences from flooding its message queue
- Scroll actions now deliver one standard wheel notch at a time, and extreme scroll
  values are rejected before a run starts
- Large native text inserts are split into bounded chunks, and control-specific
  commands are sent only to genuine standard Windows button and edit controls

## Release history

| Version | Summary |
| --- | --- |
| 3.5.0 | Browser tab automation, one target picker, pre-run checks, confirmed delivery, and profile history |
| 3.4.4 | Correct modified-hotkey capture, centered compact controls, and anchored sequence dragging |
| 3.4.3 | Overflow-only scrolling, stable window picking, recorder handoff, and UI polish |
| 3.4.2 | Complete-chord shortcut safety, earlier validation, UI containment, and project polish |
| 3.4.1 | Safer paced background delivery with responsiveness and queue-flood protection |
| 3.4.0 | Visual window picker, frozen point capture, and resize-aware window positions |
| 3.3.0 | In-app profile library with safe one-click switching and folder discovery |
| 3.2.1 | Drag-to-reorder sequence cards and corrected recovery-dialog actions |
| 3.2.0 | Background-window targeting with window-relative mouse actions and a free physical pointer |
| 3.1.0 | Moving-pointer clicks, delayed position recording, safer testing, undo, and draft recovery |
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
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

The suite covers the automation engine, cancellation and timing, profile files,
controller behavior, frozen pointer recording, visual window discovery,
resize-aware background coordinates, background-window delivery and follow mode,
draft recovery, card-only drag reordering, modal containment, responsive breakpoints,
QML loading, interaction states, and release-version consistency.

## Build a release

Build the single-file portable app:

```powershell
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm KeyClickAutomator.spec
New-Item -ItemType Directory -Force release | Out-Null
Copy-Item dist\KeyClickAutomator.exe release\KeyClickAutomator-Portable-3.5.0.exe
```

Build the installer payload, then compile it with Inno Setup 6:

```powershell
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm KeyClickAutomatorInstaller.spec
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "installer.iss"
```

Close any running release copy before rebuilding, and adjust the `ISCC.exe` path
if Inno Setup was installed somewhere else.

The Windows workflow runs the full test suite on every pull request and `main`
push. Version tags and manual runs also build both packages and produce a
`SHA256SUMS.txt` artifact.

Before publishing, complete every check in [RELEASING.md](RELEASING.md).

## Project layout

| Path | Purpose |
| --- | --- |
| `qml/Main.qml` | Tabbed desktop screens, layout, and interaction flow |
| `qml/components/` | Shared button, field, and scrollbar styling |
| `qt_controller.py` | UI model and run coordination |
| `run_session.py` | Per-profile run state for the queued and parallel runners |
| `profile_catalog.py` | Saved-profile discovery and display metadata |
| `recovery_store.py` | Atomic recovery-draft persistence |
| `shortcut_service.py` | Shortcut conflicts and global-listener formatting |
| `engine.py` | Automation actions, validation, timing, and execution |
| `window_backend.py` | Windows target discovery and background message delivery |
| `capture_overlay.py` | Frozen, dimmed multi-monitor pointer picker |
| `tests/` | Controller, engine, QML, responsive, and release tests |
| `.github/workflows/windows-ci.yml` | Windows tests, packaging, and checksums |
| `KeyClickAutomator.spec` | Single-file portable build |
| `KeyClickAutomatorInstaller.spec` | Multi-file installer payload |
| `installer.iss` | Inno Setup configuration |

## License

KeyClick Automator is available under the [MIT License](LICENSE).

## Font license

Inter is distributed under the SIL Open Font License 1.1. The full license is
included at `assets/fonts/LICENSE.txt` and packaged with the application.
