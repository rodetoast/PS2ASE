# Southpaw launcher design system

Windows Qt/Fusion client-area captures from the source commit that adds this gallery. The profile, paths, Photoshop entry and clipboard art are synthetic. These are not screenshots of the distribution EXE or tests against either host. [Previous workspace](../copied-layer-editing.png) · [User-supplied concepts](../../design-references/option-help.md)

| Workspace | Dialogs and diagnostics |
| --- | --- |
| [Empty](workspace-empty.png) · [Copied layers and enabled paste](workspace-copied.png) | [Initial setup: script warning](workspace-setup.png) |
| [390×480 logical pixels, Japanese, 200%](workspace-narrow-200.png) | [Settings](workspace-settings.png) · [Diagnostics expanded](workspace-diagnostics.png) |

**Option help:** [Ground Line](help-ground.png) · [Center](help-center.png) · [Absolute](help-absolute.png) · [Normal](help-normal.png) · [Folder → Frames](help-folder.png) · [Layer → Frames](help-layer.png)

## Design decisions

- [Launcher QML](https://github.com/rodetoast/creative-group-launcher/blob/8bb91efeeb0b67f948309eeb379cc7c37f245321/southpaw_tools/quick/Launcher.qml), [font loader](https://github.com/rodetoast/creative-group-launcher/blob/8bb91efeeb0b67f948309eeb379cc7c37f245321/southpaw_tools/quick_ui.py) and [launcher UI review](https://github.com/rodetoast/creative-group-launcher/blob/8bb91efeeb0b67f948309eeb379cc7c37f245321/docs/ui-reviews/header-branding/README.md) are the reference. Used the same OFL Pretendard Variable font, Segoe UI Variable/Segoe UI/Malgun Gothic fallbacks, and Yu Gothic UI where available for Japanese glyph fallback. Adapted the launcher's 12/14/17 px scale, 8/16 px spacing and 10/13 px radii to the existing compact tool: 13 px UI text, 15 px section titles, 5–8 px inner gaps, and 6–8 px radii. Diagnostic text keeps Consolas.
- Adopted canvas `#151822`, panel `#202432`, border `#393e51`, text `#f5f3ff`, muted `#b7b9cb`, selected tint `#302743` and primary `#7146bd`; semantic warning and success treatments retain text. Global Qt palette and main/dialog styling share the same tokens. Native Windows shell dialogs and the existing bootloader splash remain unchanged.
- The old hidden-indicator radio stylesheet still drew the text as a radio label. The workspace segments now use centered equal-width checkable buttons, with the same exclusive groups, IDs, option values and click handlers. Labels wrap at the arrow only when needed. Both edit rows stay in place; original 20 logical px SVG line icons accompany the action names, with separate disabled rendering.
- The 500 ms tooltip and F1 help show the actual Aseprite paste rules. Ground Line puts the bottom of the entire copied bounding box on the canvas midline; Center centers that box; Absolute retains metadata coordinates. One offset preserves relative layer positions. Normal uses the current frame; Folder uses one frame per folder and shared rows from the active layer down; Layer uses successive frames on one active row. The example pictures are schematic, not independent-layer alignment or a promise of global PSD coordinates.

## Verification

The full automated suite passed 121 tests (no skips). Windows QPA with Qt scale factors 1/1.25/1.5/1.75/2 checked three languages, 390×480 layout, glyph widths/equal segments, keyboard/exclusivity and tooltip delay, disabled hover, dismissal and screen bounds. Qt events were simulated; other physical monitors and screen readers were not certified. `tests/render_workspace_design.py` reproduces the captures in a temporary profile. No real host rerun, new build, ZIP, tag, or operations-catalog change.
