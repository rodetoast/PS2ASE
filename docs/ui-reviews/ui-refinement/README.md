# Workspace and setup refinement

[Before: 582f185 design review](../launcher-system/README.md) · [Original HTML concept](../../design-references/PS2ASE_UI_Design_Reference.html)

Native-resolution review sheets: [01 Workspace](review-01-workspace.png) · [02 Settings](review-02-settings.png) · [03 Help](review-03-help.png).

These client-area captures were rendered using Windows Qt/Fusion and a private synthetic profile from the development source commit that adds this gallery. No actual Photoshop or Aseprite document, user path or configuration is shown.

| View | Capture |
| --- | --- |
| Workspace, 460×620 at 100%, diagnostics closed | [Empty](workspace-empty.png) · [Copied layers](workspace-copied.png) |
| Workspace, 390×380 at 200%, Japanese | [Top of viewport](workspace-narrow-200.png) |
| Settings and warning guide | [Settings](workspace-settings.png) · [Warning](workspace-setup.png) |
| Diagnostics | [Expanded](workspace-diagnostics.png) |

Help: [Ground Line](help-ground.png) · [Center](help-center.png) · [Absolute](help-absolute.png) · [Normal](help-normal.png) · [Folder to Frames](help-folder.png) · [Layer to Frames](help-layer.png)

- Both transfer pairs fit in the first viewport at 390×380 logical pixels. Options remain scrollable below the transfer controls on short windows. The collapsed workspace does not scroll at 460×620 in the tested languages. The preview uses 48–160 logical px, retains an original raster and uses nearest-neighbor scaling at the available size and device pixel ratio. Reflection and clipboard status now share the vector icon style.
- Alignment diagrams distinguish the target midline, art-box edge and center, and the original origin and coordinates. Frame diagrams label the timeline's layer rows and frame columns. Placement and transfer algorithms were not changed.
- Settings groups connection, Aseprite installation, preferences, and help. Its confirmation footer stays accessible while the form scrolls. Script files, configured keys, Trust record and user-confirmed key operation are independent; merely opening this dialog cannot install files, approve Trust or verify host input. The guide clarifies the optional warning change and preserves all confirmation and startup flags.

## Verification

125 automated tests, plus Windows Qt 100/125/150/175/200% workspace regressions (Korean, English, Japanese, empty and populated); compact settings at 100 and 200%. The scale factors simulate DPI in Qt without modifying Windows monitor settings. Real host transfers, screening of every monitor, and packaging were not repeated. No new build, ZIP, tag or operating catalog change.

Capture script: `tests/render_workspace_design.py`; use Qt Windows scale factor 1 and 2 with high-DPI system scaling overridden for the subprocess, then run it with `--contact-sheet`.
