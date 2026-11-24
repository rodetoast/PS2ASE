# Dark workspace and setup review

Windows Qt/Fusion source-widget captures, made with test fixtures and synthetic data. The captures belong to the implementation commit that adds this page. They are not screenshots of a new packaged EXE.

| View | Before | After |
|---|---|---|
| Workspace | [previous light UI](product-workspace.png) | [dark workspace](dark-workspace.png) |
| Setup step 2 | [previous light UI](product-setup.png) | [dark warning review](dark-setup.png) |
| Diagnostics | [previous expanded UI](product-diagnostics.png) | [dark diagnostics](dark-diagnostics.png) |

The [reference set](../design-references/product-ui.md) is distinct from these implementation screenshots. The intermediate light captures [workspace](reference-followup-workspace.png) and [setup](reference-followup-setup.png) show grouping before the dark style was applied.

The main window keeps its two compact transfer rows and native Qt input semantics. Status, preview and transform tools share one panel. Alignment and frame mode are still exclusive radio groups, drawn as segments. Diagnostics stays collapsed on startup. The Photoshop connection picker and warning review remain separate; the warning review still requires explicit consent and preserves backup checks.

Verified with Windows Qt at scale 1.00/1.25/1.50/1.75/2.00 for ko/en/ja: workspace at 390×480 and all guide pages at 350×350 logical pixels, with no horizontal scrolling and guide navigation visible. No Photoshop/Aseprite or Windows Use interaction; no new EXE/ZIP.
