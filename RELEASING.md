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

## 5. Smoke-test and publish

- Launch the portable `.exe` by itself.
- Launch the installed application from its shortcut.
- Add, edit, disable, re-enable, and run a short sequence.
- Confirm `F6`, `F8`, and `F9` match the Run inspector.
- Record the SHA-256 hashes of both release files.
- Commit the source and documentation together.
- Create an annotated `vX.Y.Z` tag only after verification passes.
- Push the branch and tag, then attach both `.exe` files and hashes to the release.
