# KeyClick Automator 2.1

A polished Windows desktop utility for building keyboard and mouse automation sequences in a calm, light, system-native interface.

Version 2.1 adds a stronger Segoe UI hierarchy, higher-contrast surfaces, larger controls, a guided empty state, and restrained motion for window entrance, status changes, and indefinite-run progress.

## Actions
- Key press
- Multi-key hotkey
- Typed text
- Left, right, middle, and double click
- Scroll at a recorded screen position
- Drag from one recorded position to another
- Per-action repeat count and delay
- Enable/disable an action without deleting it

## Run controls
- Exact whole-sequence cycle count or an explicit **Loop indefinitely** mode
- Start countdown
- Delay between cycles
- Text typing speed
- Optional timing variation
- Live cycle progress
- Customizable global Start/Toggle, Capture Position, and Emergency Stop shortcuts
- PyAutoGUI screen-corner emergency fail-safe

## Workflow
- Reorder, duplicate, edit, delete, or temporarily disable actions
- Save and load reusable `.kca.json` profiles
- Optional always-on-top window
- Portable executable and per-user installer

## Quick start
1. Choose an action in the Inspector.
2. For a key action, click **Press to record a key** and press the key you want.
3. For mouse actions, use **Capture cursor position** or the configured Capture shortcut.
4. Add the action to the sequence and arrange it in the required order.
5. Open the **Run** Inspector tab and set the stop mode, timing, and shortcuts.
6. Start with one cycle while testing. Use the configured Start shortcut or click Start.
7. Use the configured Emergency Stop shortcut at any time to stop.

Key names follow PyAutoGUI conventions, such as `enter`, `space`, `tab`, `esc`, `left`, `right`, `f1`, and letters/numbers. Hotkeys use `+`, for example `ctrl+shift+s`.

The currently configured global shortcuts are reserved and cannot also be used as executable key actions.

## Safety
- Test unfamiliar sequences with one cycle first.
- F9 stops the active run.
- Moving the cursor to a screen corner triggers the PyAutoGUI fail-safe.
- Do not use the application for passwords, payment screens, bypassing protections, spam, or systems you do not own or have permission to automate.

## Development
```text
python -m pip install -r requirements.txt
python app.py
python -m pytest -q
```

## Build
```text
pyinstaller KeyClickAutomator.spec --clean --noconfirm
```
