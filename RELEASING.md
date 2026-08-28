# Releasing KeyClick Automator

A version bump is not complete until the application metadata, README, tests,
and both Windows builds all describe the same release.

## 1. Update the version

Use the same `MAJOR.MINOR.PATCH` value in every location:

- `qt_controller.py` — `APP_VERSION`
- `installer.iss` — `MyAppVersion`, `OutputBaseFilename`, and `VersionInfoVersion`
- `version_info.txt` — `FileVersion` and `ProductVersion`
- `README.md` — current release, build filenames, What's New heading, release history, and build commands

The release metadata test checks these locations. Do not weaken the test to make
an inconsistent version pass.

## 2. Write the release notes

In `README.md`:

1. Rename the **What's new in X.Y.Z** heading.
2. Replace its bullets with user-visible changes from the new release.
3. Add the version to the top of **Release history**.
4. Keep the instructions written for someone using KeyClick for the first time.

## 3. Verify the source

```powershell
.venv\Scripts\python.exe -m pytest -q
git diff --check
```

## 4. Build both packages

Close every running release copy first so Windows does not lock an executable
that needs to be replaced.

Portable build:

```powershell
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm KeyClickAutomator.spec
New-Item -ItemType Directory -Force release | Out-Null
Copy-Item dist\KeyClickAutomator.exe release\KeyClickAutomator-Portable-X.Y.Z.exe
```

Installer build:

```powershell
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm KeyClickAutomatorInstaller.spec
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" "installer.iss"
```

If a trusted Windows code-signing certificate is configured, sign both `.exe`
files now. Never describe a build as signed unless `Get-AuthenticodeSignature`
reports `Valid` for that exact file.

Generate the checksum manifest after any signing step so its hashes match the
files users download:

```powershell
$files = Get-ChildItem release\KeyClickAutomator-*.exe | Sort-Object Name
$lines = foreach ($file in $files) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    "$hash *$($file.Name)"
}
$lines | Set-Content -Encoding ascii release\SHA256SUMS.txt
```

## 5. Smoke-test and publish

- Launch the portable `.exe` by itself.
- Launch the installed application from its shortcut.
- Add, edit, disable, re-enable, and run a short sequence.
- Confirm a fixed pointer position hides KeyClick, freezes and dims every monitor,
  records the clicked point without activating the underlying app, and lets `Esc`
  cancel safely.
- Confirm **Follow current pointer** clicks without moving the pointer back to a
  saved position.
- In **Background window** mode, confirm the visual picker shows Desktop and open
  app windows, refreshes its list, marks the selected target, and disables
  minimized windows until they are restored.
- Record a relative click, resize the target in both directions, cover it with
  another window, and confirm the click tracks the same relative location without
  moving the physical pointer or stealing focus. Repeat with both endpoints of a
  drag action.
- Confirm a minimized, closed, or higher-privilege target produces a clear
  recovery message instead of falling back to desktop input.
- With the target covered, repeat a zero-delay background click at least 100 times
  and confirm the target stays responsive. Verify scroll is delivered as individual
  notches and an unresponsive target is rejected before more input is posted.
- Confirm **Test once**, **Run from here**, delete undo, and draft recovery.
- Confirm sequence cards drag by their six-dot grip, show one insertion guide,
  land in the expected order, and still move with **Up**/**Down**. During the drag,
  only the card moves; its numbered badge and connector stay anchored.
- Confirm the recovery and unsaved-changes dialogs keep every action fully inside
  the modal at the minimum supported window size.
- Confirm **Profiles** lists sibling `.kca.json` files, marks the current profile,
  switches without a system dialog, and protects unsaved changes.
- Confirm **Change**, **Open file…**, `Ctrl+S`, and `Ctrl+Shift+S` update the profile
  folder and list as documented.
- Confirm `F6`, `F8`, and `F9` match the Run inspector.
- Verify the two entries in `SHA256SUMS.txt` against the final release files.
- Commit the source and documentation together.
- Create an annotated `vX.Y.Z` tag only after verification passes.
- Push the branch and tag, then attach both `.exe` files and `SHA256SUMS.txt` to
  the release.
