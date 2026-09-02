# Handoff — 3.5.0 branch

Everything below is on `feat/runner-tabs-and-fixes`, 12 commits ahead of `main`,
pushed and in sync with origin. **236 tests pass.** `main` is untouched and there
is no `v3.5.0` tag yet (latest tag is `v3.4.4`).

```powershell
.venv\Scripts\python.exe -m pytest -q      # 236 passed
.venv\Scripts\python.exe qt_app.py         # run it
```

---

## 1. Decisions waiting on the owner

**a. Tabbed navigation — unresolved.** Sequence / Profiles / Runner replaced a
left rail and two side drawers. After using it the owner said *"the logic and the
flow of the app is so messed up now… as a user you would be freaking confused."*
Nothing was reverted, and no replacement was agreed.

The one concrete report from that session turned out to be a data-loss bug rather
than a layout problem (see §4), and it is fixed — so the tabs may be in better
shape than when they were judged. Worth a fresh look before deciding.

Do **not** redesign this from a mockup. That is exactly how it went wrong: a
picture was approved, the build was validated against a headless renderer and a
green suite, and it was still confusing in the hand. Watch the owner do one real
task instead.

**b. The release is staged but unpublished.** See §3.

---

## 2. Refactor: unfinished

The goal is **no file over 600 lines**. **Every QML file is now under it.** Five
remain, all Python:

```
1704  tests/test_qt_controller.py
1383  qt_controller.py
1315  tests/test_qml_smoke.py
 825  controller_running.py
 616  tests/test_engine.py
```

Already split: `Main.qml` 3504→1958→**456**, `qt_controller.py` 2956→1383,
`window_backend.py` 866→299, and `controller_running.py` 1071→825.

`Main.qml` came apart into `components/AppHeader.qml` (127),
`components/RunBar.qml` (153), `pages/SequencePage.qml` (511), and the inspector,
which was 818 on its own and split again into `components/RunInspector.qml` (133,
the shell and tab bar), `components/ActionEditorForm.qml` (464) and
`components/RunSettingsForm.qml` (268). Each form owns the `Connections` handlers
that write into its own fields; only `onToast` stayed on the root.

### What each remaining split needs

- **`qt_controller.py` → ~500.** Two more mixins: `controller_actions.py`
  (ActionListModel + action CRUD) and `controller_targeting.py` (window, browser,
  unified picker).
- **`controller_running.py` → ~450.** Split sessions/workers from progress and
  completion reporting.
- **Test files.** Split to mirror the source modules.

### How the existing splits work

Python is split into **mixins**, not separate objects. PySide6 registers
`Property`, `Slot`, and `Signal` from a plain (non-QObject) mixin as long as the
final class is a `QObject`, so the controller stays one object with an unchanged
QML surface:

```python
class AutomatorController(QueueMixin, RunningMixin, CaptureMixin, ProfilesMixin, QObject)
```

All signals live in `controller_signals.py` because a property's `notify=`
argument needs the Signal object in scope where the property is declared. Inside
a mixin you must write `notify=ControllerSignals.somethingChanged` — a bare name
will not resolve, because inherited attributes are not in scope during class-body
execution.

QML is split under `qml/`: `Theme.qml` (singleton, registered via `qml/qmldir`
and `engine.addImportPath`), `components/`, `pages/`, `dialogs/`. Extracted files
take an `app` property pointing at the application root instead of reaching an
outer id. Their ids stay at the call site in `Main.qml`, so the root functions
that open them are unchanged.

### Six traps this refactor hit — expect them again

1. **Splitting on a line boundary cuts a decorator from its method.** Happened
   four times (`_path_key` twice, `startPositionCapture`, `recoverDraft`). The
   symptom is an `IndentationError`, or worse, a `@staticmethod` silently landing
   on the wrong method. Always split *above* the decorator.
2. **A moved symbol changes where tests must patch it.** `AutomationRunner` is
   resolved in `controller_running` now, so `monkeypatch.setattr(qt_controller,
   "AutomationRunner", …)` silently stops working. Patch where it is *used*.
3. **`controller: controller` on an extracted component shadows the context
   property with itself.** Tests passed; the running app was full of
   `ReferenceError`. Do not re-declare `controller` — it is global.
4. **Relative asset paths break one directory down.** `"../assets/…"` from
   `qml/pages/` resolves nowhere, and QML does not error on a missing image — it
   just draws nothing. `test_split_qml_files_reference_assets_from_their_own_directory`
   guards this now.
5. **A property assigned from the id of the same name binds to itself.**
   `RunBar { runForm: runForm }` reads perfectly and silently resolves to the
   RunBar's own null property, not to the form. Give one of the two a different
   name — the inspector publishes `runSettingsForm` and the id stays `runForm`.
   This is trap 3 wearing a different hat.
6. **An id is invisible outside the file that declares it, and nothing warns.**
   `RecoveryDialog.qml` called `editor.loadAction(...)` for who knows how long;
   `editor` evaluated to `undefined` and the call threw the moment anyone
   recovered a draft with an action selected. It goes through
   `app.loadActionIntoEditor(index)` now, and
   `test_no_qml_file_calls_through_an_id_that_lives_in_another_file` fails on any
   new instance.

Also: **`test_qml_design_contract.py` pins literal QML text**, including `root.`
prefixes. Renaming a receiver during a split breaks assertions that have nothing
to do with what changed. Five needed updating here (the logo path, two
`root.beginSequenceDrag`/`updateSequenceDrag` calls, two
`root.shortcutRecordingTarget` ones); the precedent from the earlier split is to
loosen the prefix rather than pin the new one.

---

## 3. Release 3.5.0 — staged, not published

Done: version consistent everywhere, README and `release/RELEASE_NOTES-3.5.0.md`
rewritten, both packages built, `SHA256SUMS.txt` generated, portable build
launched successfully.

**Not done, deliberately:** `RELEASING.md` step 5 is a ~15-item manual smoke test
(recording a pointer position on a frozen screen, resizing a target and checking
the click tracks, dragging sequence cards, dialogs at minimum window size, F6/F8/F9),
and the checklist says to tag **only after** it passes. Tagging without it would
assert a verification that never happened.

Worth adding to that pass, since nothing has exercised them by hand:
- **Start browser → pick a tab → record by clicking in the page → run**, and check
  the completion message names the element it hit.
- **Profiles → ↺** and confirm the version list looks right.

⚠️ **The artifacts in `release/` were built before the refactor commits.** They are
functionally equivalent but not built from branch HEAD. Rebuild before tagging.

When it passes:

```powershell
git tag -a v3.5.0 -m "KeyClick Automator 3.5.0"
git push origin v3.5.0
gh release create v3.5.0 -F release/RELEASE_NOTES-3.5.0.md `
  release/KeyClickAutomator-Portable-3.5.0.exe `
  release/KeyClickAutomator-Setup-3.5.0.exe `
  release/SHA256SUMS.txt
```

---

## 4. Data loss that already happened

`Cookie Clicker.kca.json` and `Click the button.kca.json` in the repo root were
**emptied** during a session — synthetic clicks driven into the live app hit Save
over an empty sequence. Their `settings` survived; their `actions` did not, and
no recovery draft existed.

The Cookie Clicker sequence was one Left click, window-relative **(283, 476)**,
scales-with-window, wait 0.1s. The other was never observed and must be re-recorded.

Two guards came out of this and both are in:
- Every save and delete snapshots the file first into `.keyclick-history`
  beside it, restorable from the Profiles page (`profile_history.py`).
- **Do not drive the running app with synthetic mouse input.** Launch it and let
  the owner click. Screenshots are fine (read-only); `SetCursorPos` + `mouse_event`
  is what caused this.

---

## 5. Things learned that are not obvious from the code

- **Background-window mode cannot click a web page, at all.** Browsers composite
  the page themselves and leave no child window under it; every click point in
  Chrome resolves to the root `Chrome_WidgetWin_1`. This wasted a whole session
  before it was diagnosed. `preflight.py` now refuses the combination by name.
- **Browser automation needs its own Chrome profile.** Chrome 136+ refuses
  `--remote-debugging-port` against the default user-data-dir. A persistent
  profile lives beside the app data; the owner's game saves are *not* in it.
- **Zero delay delivers fewer clicks, not more.** Measured against Cookie Clicker:
  0.000s → 20/40 registered; 0.017s → 40/40. Pages ignore input faster than they
  can process.
- **Chrome rejects a browser-style `Origin` on the debugger socket.** Send none
  (`suppress_origin=True`) rather than opening it up with `--remote-allow-origins=*`.
- **`websocket-client` is imported lazily inside a function**, so PyInstaller
  cannot infer it. It is in both `.spec` files' `hiddenimports` with a test
  guarding it. Without that, a packaged build ships with browser mode broken while
  the dev build works fine.
- **Do not benchmark a Qt worker thread under `QTest.qWait`.** Polling starves it
  of the GIL and made CDP calls look like 274ms when they are 4.4ms under a real
  `app.exec()`. This nearly caused a fix for a non-existent performance bug.
- **A green suite does not mean the UI is intact.** A pure refactor with 235
  passing tests still shipped blank profile icons. Render and look.
  `tests/test_qml_component_boundaries.py` now reads the QML warning stream while
  walking every tab, inspector tab and breakpoint, which catches the unresolved
  reference class of that bug without a human. It does not catch "renders, looks
  wrong" — that still needs eyes on a screenshot.

---

## 6. Open items not yet started

- `enqueueCurrentProfile` and `runQueueActiveCount` on the controller have no QML
  callers; only tests exercise them. Wire up or drop.
- `_start_parallel_queue`'s `started == 0` branch is unreachable.
- The `venv` had no `pip` until `ensurepip` was run for `websocket-client`.
