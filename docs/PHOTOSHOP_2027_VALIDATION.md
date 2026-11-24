# Photoshop 2027 verification - 2026-11-24

## Identity and scope

- Candidate: Ase-PS Bridge Pro 0.3.7, app_id `ps2ase`, executable `bridge_ui.exe`.
- Windows 11 x64; Photoshop executable product **Adobe Photoshop 2027**, file version **28.0 (20261027.r.20 3951c45)**; scripting runtime **28.0.0**.
- Executable: `C:/Program Files/Adobe/Adobe Photoshop 2027/Photoshop.exe`.
- Photoshop 2026 (27.11) is also installed; 2025 directory has no Photoshop.exe. Neither older version was exercised in this task.
- Registry `Photoshop.Application.210` resolves to 2027 CLSID `{1271048C-E6B0-4EB2-96C5-F5EEC769A313}` and its exact LocalServer32. Generic `Photoshop.Application`/CurVer still selects `.200` (2026). The application uses the selected EXE and validates app.path + internal major before executing JSX; it does not fall back to generic COM.
- The original Desktop dirty checkout and v0.3.6 tag are unchanged. The isolated candidate starts from `codex/migration-checkpoint-20261117`, incorporates the latest selected local source/tests, and adds the missing Splash bitmap. Raw hash differences for several checkout files were line endings, not missing algorithm changes.

## Changes

- Derive the settings year from the verified EXE's exact release product name; retain known legacy-major fallback and reject Beta, unknown/ambiguous products and known-major/product disagreement. Only an existing exact settings folder is accepted. No preferences directory or security setting is created by detection.
- Make spec entry relative to this checkout, not an absolute path to the older Desktop checkout. Preserve Splash and ICU guard, icons and script contents. Add Windows product/file version resource 0.3.7 without renaming the app.
- Retain all previous source-safety, diagnostics, preview layout, startup, first-run and Copy-cost changes.
- Test fixtures support a clean checkout and an explicit `NODE_BINARY`; isolate the baseline Git invocation from inherited temporary command-line configuration.

## Real-host evidence

The opt-in `tests/host_photoshop_probe.py` creates only synthetic RGB/8 documents, uses the version-specific COM ProgID for setup and a separate Aseprite 1.3.18.6 batch process. It closes only documents it created and compares the original open-document ID set afterwards. No user's existing Aseprite window/document was controlled.

| Test | Result |
|---|---|
| Version-specific COM identity | 28.0.0 / exact 2027 path |
| Normal, Folder Frames, Layer Frames via production CLI worker | Pass, completion + per-attempt responses |
| Each mode x Absolute / Center / Ground Line | 9/9 pass; extracted RGBA equals imported cel RGBA; placement formula and opacity checked |
| Original synthetic PNG vs extracted image | Nontransparent cropped RGBA agrees, including alpha 128 |
| Directly selected nested folders | Two independent frame containers, not their common parent |
| Folder row order / reuse / fewer rows | Row 1 A/D, row 2 B/empty, row 3 C/empty; active row included, downward direction |
| Layer Frames | A/B/C/D on four frames of one target row |
| Aseprite Copy -> Photoshop Paste | 4 layers, 128x128; alpha and rendered pixels agree with metadata positions |
| Document safety | Initial/final Photoshop document ID set equal for completed full probe |
| Photoshop initially stopped | Selected 2027 EXE starts and returns the expected no-document error in 11.47s; started marker present, no success marker |
| Packaged Onefile Normal Copy | Actual GUI click -> 3-layer result and Preview; thread finishes and buttons recover |
| Packaged Onefile reverse Paste | Actual Aseprite batch Copy into the EXE's active_temp_path -> GUI Paste -> 4 layers; alpha/rendered pixels/coordinates pass |
| Packaged settings | 2027 (28.0) and 2026 (27.11) listed separately; exact saved 2027 path and selected combo restored on opening Settings |

Fully transparent RGB bytes can change in Photoshop PNG saves (e.g. transparent white instead of transparent black). Reverse comparison requires identical alpha and identical rendering over black, not irrelevant hidden RGB equality. No image-processing code was changed for this difference.

Completed CLI sample times were Normal 11.118s, Folder 13.155s, Layer 9.083s, including human confirmation and routing overhead. These single samples do not establish a performance improvement or regression. No 8007 occurred in these completed probes; its underlying cause remains unproven.

## Failures distinguished from passes

- Initial probe setup incorrectly assumed COM JavaScript globals persisted between calls; the probe was corrected to reacquire its source by captured document ID. A known synthetic document left by the failed probe was identified and closed; no user document was touched.
- Aseprite Sprite construction starts with a blank cel; the fixture now removes that fixture-owned cel before import. Korean batch output decoding was made explicit. These were test-tool changes, not production paste fixes.
- The first CLI attempt expired before manual warning approval; its token prevented late execution from becoming a success. Human approval probes allow 120s only in the test tool; production timeout remains 30s.
- The first packaged reverse click also expired before approval. Buttons recovered. A subsequent foreign-root payload had no metadata in the EXE's job root; it returned a script error instead of success. The correct test then used a newly generated Aseprite Copy under the EXE's actual active_temp_path and passed. No cross-root/pipeline feature was added.

## Automation and packaging

- 113 tests, no failures/errors/skips (111 preserved + 2 new compatibility cases). Includes the original failure-injection document protection and v0.3.6 metadata comparison.
- Python compilation, both JSX syntax checks with only #target removed for Node, spec parsing and Git whitespace check passed.
- Onefile: Python 3.12.14, PyInstaller 6.22.3, clean private venv/PATH. Qt-required missing-import warning search is empty. Actual GUI launches without Qt/ICU or missing-module traceback.
- Archive reader confirms icon, Splash and four scripts equal the candidate inputs byte-for-byte; QtCore/QtWidgets DLLs present. The built EXE product/file version is 0.3.7.
- No legacy Desktop build/dist files were overwritten. ZIP is a separate handoff candidate, not an operational GitHub Release.

## Limits

- Actual 2024/2025/2026, every DPI/display/Windows build, large production PSDs, all blend modes/color depths and repeated 8007 reproduction are not certified by these synthetic tests.
- Existing F4/F5 GUI hotkey routing and first-time Aseprite Trust are reused from prior results, not newly approved in the user's active Aseprite. Batch host verification is distinct from hotkey/UI permission verification.
- Security warning settings were not changed. The user personally approved external script prompts. A prompt left unanswered can still time out safely.
- Do not execute the previously flagged startup_manual_probe, qt_loader_probe or startup_runtime_probe. They are not bundled and were not run.
- Operational catalog signing/publication and employee rollout belong to the launcher project after separate approval.
