# Launcher handoff: ps2ase 0.3.7 candidate

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
- Latest bundled Aseprite scripts are compared/copied at startup. Trust is a separate user approval, not inferred from copying. If Aseprite does not reload a changed script/key map, restart it and use the existing reinstall control if needed.
- External JSX execution warnings remain enabled unless the user independently configured them. The user must approve actual requests; unanswered prompts can time out and are not silently retried.

## Verified versus pending

113 automated tests pass, no skips. Real Photoshop 2027 28.0.0 / Aseprite 1.3.18.6 synthetic tests cover the three modes x three Aseprite alignments, order/frames/empty rows, actual reverse Copy/Paste and alpha/rendered-pixel comparison. The packaged EXE's Normal Copy/Preview and reverse Paste also pass. Installed-version list distinguishes 2026 and 2027 and restores the exact saved 2027 target.

Older Photoshop real runtime, existing GUI F4/F5 and initial Trust, every DPI/Windows combination and production PSD variations remain unverified in this task. See [detailed evidence](PHOTOSHOP_2027_VALIDATION.md) and [employee release notes](../RELEASE_v0.3.7.md).

## Launcher owner's next steps

Import this exact ZIP, verify size/hash/entrypoint and retained paths, and perform the launcher-specific upgrade/start/rollback checks. Source push is not catalog approval. Catalog signing, sequence increment, operational GitHub publication/Latest and employee rollout require separate approval in the launcher project. Operational PS2ASE remains 0.3.6 until then. No v0.3.6 tag was changed and no new release tag was created here.

## Central hub synchronization pending

Project source/handoff development commits were pushed to PS2ASE. Hub summary/list changes are committed locally as `9338317` on `codex/ps2ase-2027-candidate-20261124`, but push was denied with HTTP 403 for the sole configured account `toast-source`. No credentials or access controls were changed. `development-hub-ps2ase-2027.patch` is beside the candidate for an authorized hub maintainer. The operational hub main and its remote development branch have not been updated by this task.
