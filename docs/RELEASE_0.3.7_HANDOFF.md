# Launcher handoff: ps2ase 0.3.7 candidate

## RC2 (2026-11-27)

**Candidate only. No operating Release, Latest, signed catalog, or employee rollout change.**

| Field | Value |
|---|---|
| Product / catalog display | Photoshop ↔ Aseprite |
| app_id / version | `ps2ase` / `0.3.7` |
| release_id | `0.3.7-rc2-eadff73` |
| Product source | [eadff73280bfb7b9dd491af406d6c3d4385e6e5a](https://github.com/rodetoast/PS2ASE/commit/eadff73280bfb7b9dd491af406d6c3d4385e6e5a) on `codex/photoshop-2027-candidate-20261124`; later docs-only changes are not build inputs |
| Local transfer source | `C:/Dev/PS2ASE-release-0.3.7-rc2-20261127/ps2ase--0.3.7-rc2-eadff73.zip`; copy the exact ZIP and `SHA256SUMS.txt` to the test PC via an approved transfer channel. No remote artifact was uploaded here. |
| ZIP bytes / SHA-256 | 59,384,190 / `4990E0D607B0C23F608F9EB71B9FF73580D93EE9BF99F59521F1E71D233CE1DB` |
| EXE bytes / SHA-256 | 59,797,103 / `EF956480C0769C924D18B19A73F3F02206258C5BA68F7557D3C70857226925F4` |
| ZIP root / entrypoint | `bridge_ui.exe` and `RELEASE_v0.3.7.md` only; launch `bridge_ui.exe` from its installation directory |
| Build | Windows x64 PyInstaller 6.22.3 Onefile with bootloader Splash; Python 3.12.14, PySide6 6.12.0, Pillow 13.0.0 |

`handoff.json`, `SHA256SUMS.txt`, and `archive-check.json` are beside the ZIP. Build/smoke logs, caches, and test profiles are not part of the delivery. The RC1 local EXE and ZIP still match their recorded hashes.

- Preserve `%APPDATA%/Ase-PS-Bridge` (settings/logs), `%APPDATA%/Aseprite` (scripts/keys/permissions), and writable `temp/` beside the EXE. Stop Bridge before switching its files; do not close host apps or remove data as part of an update. Retain the existing launcher install and working directory contract.
- RC2 compares installed scripts to bundled files but does not install or update scripts or F4/F5 at startup. Use the guide or Settings to confirm the change after Aseprite closes; preserve backups, conflict checks and existing Trust. Script access prompts are answered in Aseprite. Photoshop JSX warnings remain enabled unless the user chooses otherwise.
- 158 source tests passed (0 skipped). Verified PE x64 GUI, icon, display name and 0.3.7 version resource, bootloader Splash, required Qt/COM binaries, and all 15 assets/scripts byte-for-byte, including the PSD, Aseprite exercise and font license. Verified ZIP integrity and embedded EXE hash. Isolated Onefile startup reached `STARTUP_INTERACTIVE` without an exception or Aseprite profile writes. This was an offscreen startup with existing settings, not a visual or host-interaction test.
- Reused earlier Photoshop 2027/Aseprite host evidence and independent source results for [#1](https://github.com/rodetoast/southpaw-development-hub/issues/1#issuecomment-7212264991) and [#2](https://github.com/rodetoast/southpaw-development-hub/issues/2#issuecomment-7216568479), both closed. The independent input tests used Windows automation, not physical keys. RC2 packaged host transfers and cross-PC setup are pending; Photoshop 2026 and older were not retested.

### Test PC: exact RC2 package

1. Copy only the candidate ZIP/checksums and verify both SHA-256 values and sizes before launch. Extract to a separate writable Windows x64 folder; do not replace RC1 or the installed operational version.
2. Use an isolated APPDATA profile and synthetic data. Verify bootloader Splash handoff, first-run language/guide, icon, font, tutorial images, exercise files and startup with existing settings. Compare settings and Aseprite script/key files across startup to confirm there are no unapproved writes.
3. With the test Aseprite closed, explicitly approve installation or update. Verify script hashes against the product commit and verify shortcut/backup behavior. Use only the test profile to approve script access, then verify F5 practice and F4 on active/closed Unicode practice tabs. Check that guide completion and restart preserve unrelated clipboard data.
4. Report package SHA, Windows/Aseprite versions and outcomes. If Photoshop is unavailable, leave packaged Photoshop transfer pending; confirm on the development PC only if needed, with an isolated Normal Copy/Paste case and direct user confirmation of any host prompt.
5. Launcher owner: check import, retained paths, upgrade/start/rollback using this exact ZIP. Make no operational catalog/signing/Latest change without separate approval.

## RC1 archive (2026-11-24)

Prepared 2026-11-24. **Not an operational release or employee rollout approval.**

| Field | Value |
|---|---|
| Product | Ase-PS Bridge Pro |
| app_id | `ps2ase` (unchanged) |
| Product version | `0.3.7` |
| Candidate release_id | `0.3.7-rc1-74f57bb` |
| Source commit | `74f57bbf9c01443d1eda6267559762a1088a9236` |
| Source branch | `codex/photoshop-2027-candidate-20261124` |
| ZIP filename | `ps2ase--0.3.7-rc1-74f57bb.zip` |
| ZIP bytes | `55955225` |
| ZIP SHA-256 | `E6A3E7EC192E8419DBF12FF93D2C0E580A872B38AFC4BC2E61CA80F6191D965A` |
| EXE filename | `bridge_ui.exe` (unchanged) |
| EXE bytes | `56345607` |
| EXE SHA-256 | `83151642F94B59B4AAC9801C70AE3EC47199DF9B623365EA79A15A0478AE039E` |
| Packaging | Windows x64 PyInstaller Onefile; ZIP root contains EXE + RELEASE_v0.3.7.md only |

The local candidate and `handoff.json`/`SHA256SUMS.txt` are under `C:/Dev/PS2ASE-release-0.3.7-20261124/`. They are not committed. The source commit identifies the code/spec/resource inputs. Subsequent documentation-only commits do not change these bytes; do not rebuild or replace this same release_id with different bytes.

## Existing install/update contract

- Preserve app_id and launch `bridge_ui.exe` with its installation directory as working directory. No rename, icon change, new daemon or launcher readiness protocol was introduced.
- Preserve `%APPDATA%/Ase-PS-Bridge` (settings/logs), `%APPDATA%/Aseprite` (scripts/keys/permissions), and writable `temp/` next to the EXE. Do not reset settings or first-time Trust on update.
- Stop Bridge before switching its installed files. Do not terminate user Photoshop/Aseprite processes. Avoid updating while a transfer is active; preserved clipboard payloads can reference the previous temp path.
- Keep the current launcher's existing installation/retained-path policy; do not invent a new manifest/Bootstrap contract for this legacy onefile package.
- RC1 used startup script synchronization. This describes that historical binary only; RC2 uses the explicit approval policy above. Trust remains a separate user approval.
- External JSX execution warnings remain enabled unless the user independently configured them. The user must approve actual requests; unanswered prompts can time out and are not silently retried.

## Verified versus pending

113 automated tests pass, no skips. Real Photoshop 2027 28.0.0 / Aseprite 1.3.18.6 synthetic tests cover the three modes x three Aseprite alignments, order/frames/empty rows, actual reverse Copy/Paste and alpha/rendered-pixel comparison. The packaged EXE's Normal Copy/Preview and reverse Paste also pass. Installed-version list distinguishes 2026 and 2027 and restores the exact saved 2027 target.

Older Photoshop real runtime, existing GUI F4/F5 and initial Trust, every DPI/Windows combination and production PSD variations remain unverified in this task. See [detailed evidence](PHOTOSHOP_2027_VALIDATION.md) and [employee release notes](../RELEASE_v0.3.7.md).

## Launcher owner's next steps

Import this exact ZIP, verify size/hash/entrypoint and retained paths, and perform the launcher-specific upgrade/start/rollback checks. Source push is not catalog approval. Catalog signing, sequence increment, operational GitHub publication/Latest and employee rollout require separate approval in the launcher project. Operational PS2ASE remains 0.3.6 until then. No v0.3.6 tag was changed and no new release tag was created here.

## Historical RC1 central hub synchronization note

Project source/handoff development commits were pushed to PS2ASE. Hub summary/list changes are committed locally as `9338317` on `codex/ps2ase-2027-candidate-20261124`, but push was denied with HTTP 403 for the sole configured account `toast-source`. No credentials or access controls were changed. `development-hub-ps2ase-2027.patch` is beside the candidate for an authorized hub maintainer. The operational hub main and its remote development branch have not been updated by this task.
