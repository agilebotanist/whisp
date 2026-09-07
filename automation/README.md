# Automation scripts

Installable macOS integrations that wrap the `whisp` CLI, so you don't have to open a terminal every time. See the main [README.md](../README.md#finder-integration) for what each one does and when to use it. This directory has the actual installable files.

All of these require `whisp` to already be installed and on `PATH` (`pipx install .` from the repo root — see the main README). They resolve its location automatically at install time; if you later move or reinstall `whisp` somewhere else, just re-run the relevant install script.

## Right-click Quick Action

```bash
automation/install-quick-action.sh     # installs
automation/uninstall-quick-action.sh   # removes
```

Installs `Transcribe with Whisp.workflow` into `~/Library/Services`. Right-click any audio file or folder in Finder → **Quick Actions → Transcribe with Whisp**. Runs silently (`--srt --quiet`) with a "starting" and a "done" notification — no Terminal window.

The `.workflow` bundle here is a template: its script has a `__WHISP_BIN_DIR__` placeholder that the install script substitutes with your actual `whisp` location (Quick Actions run in a bare shell that never sources `.zshrc`, so a plain `whisp` command name alone wouldn't resolve).

## Folder Action (zero-click, auto-transcribe on drop)

```bash
automation/install-folder-action.sh <folder>     # attach
automation/uninstall-folder-action.sh <folder>   # detach
```

Watches `<folder>` and transcribes any audio file added to it — no click at all, just drop the file in. Implemented as a compiled AppleScript (`Auto-transcribe.applescript` → `.scpt`), the traditional Folder Actions mechanism, attached via `System Events`. Output goes to `<folder>/Transcripts`, not `<folder>` itself — writing output back into the watched folder would count as a new item and re-trigger the action on itself.

Only affects files added *after* installation; anything already in the folder when you attach it is left alone. Safe to attach to multiple folders — they share one compiled script.

## Desktop shortcut (double-click, fixed folder)

```bash
automation/make-desktop-shortcut.sh <folder> [name] [-- whisp-args...]
```

Generates a double-clickable `.command` file on your Desktop that opens Terminal, runs `whisp <folder>` with visible progress, and waits for a keypress. Defaults to `--srt`; pass your own flags after `--`, e.g.:

```bash
automation/make-desktop-shortcut.sh ~/Voice\ Memos "Transcribe Voice Memos" -- --srt --verbose
```

Unlike the other two, this one re-runs on the whole folder every time you double-click it — it doesn't track what it already transcribed, so repeated runs on a growing folder will re-transcribe everything, not just what's new.

## Notes for maintainers

- Every script here is idempotent and safe to re-run.
- All three were verified end-to-end on real hardware while building them (real Quick Action registration confirmed via `com.apple.ServicesMenu.Services`, real Folder Action attach/detach via `System Events`, real transcription output produced in each case) — not just written and assumed to work.
- The `Transcribe with Whisp.workflow` and `Auto-transcribe.applescript` schemas were reverse-engineered from real Apple-shipped examples (`/System/Library/Services/Encode Selected Audio Files.workflow`, `/System/Library/PrivateFrameworks/FolderActionsKit.framework`), not guessed from memory.
