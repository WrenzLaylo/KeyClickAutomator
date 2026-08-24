# KeyClick Automator 3.0

A modern Windows desktop utility for building reliable keyboard and pointer automation sequences.

Version 3.0 replaces the previous CustomTkinter interface with a GPU-rendered PySide6 / Qt Quick interface. The new layout adapts at real breakpoints instead of squeezing three fixed columns, eliminating the clipping and redraw issues seen during window resizing.

## What is new in 3.0

- Responsive wide, medium, and compact layouts
- Compact navigation rail at smaller widths
- Slide-over inspector at laptop-sized widths
- Bundled Inter Regular, Medium, SemiBold, and Bold fonts
- Smooth Qt Quick layout, color, press, drawer, progress, status, and sliding-tab animations
- Stronger light theme with layered surfaces and restrained ambient color
- Keyboard-accessible controls with clear focus states
- Indefinite loops with an animated progress state
- Custom Start, Capture, and Emergency Stop shortcuts
- One-click “Listen for a key” capture for key actions
- Existing `.kca.json` profile compatibility

## Supported actions

- Key press
- Multi-key shortcut
- Type text
- Left, right, double, and middle click
- Scroll
- Pointer drag

Every action can be enabled or disabled, repeated, delayed, reordered, duplicated, edited, and deleted.

## Run controls and safety

- Finite cycle counts or `Loop indefinitely`
- Start countdown
- Delay between cycles
- Typing interval
- Optional timing variation
- Global Start / Toggle shortcut
- Global pointer capture shortcut
- Global Emergency Stop shortcut
- PyAutoGUI corner fail-safe remains active
- Automation runs on a worker thread so Stop remains responsive

Defaults:

- `F6` — Start / Toggle
- `F8` — Capture pointer position
- `F9` — Emergency Stop

## Run from source

```text
C:\Users\OASIS\Downloads\KeyClickAutomator\.venv\Scripts\python.exe qt_app.py
```

## Test

```text
C:\Users\OASIS\Downloads\KeyClickAutomator\.venv\Scripts\python.exe -m pytest -q
```

The test suite covers the automation engine, cancellation, timing, profiles, controller operations, responsive breakpoints, QML loading, and resize-state behavior.

## Release artifacts

- `release\KeyClickAutomator-Portable-3.0.0.exe`
- `release\KeyClickAutomator-Setup-3.0.0.exe`

The installer is per-user and does not require administrator rights.

## Font license

Inter is distributed under the SIL Open Font License 1.1. The complete license is included at `assets\fonts\LICENSE.txt` and is packaged with the application.
