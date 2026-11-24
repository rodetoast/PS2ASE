# Photoshop ↔ Aseprite UI review

Windows Qt/Fusion source captures with an isolated test profile. The displayed Photoshop status and log entry are examples, not live host evidence. These captures are committed alongside their implementation and are not included in the release bundle.

- [Workspace](product-workspace.png): empty preview, grouped transfers, diagnostics closed.
- [Setup guide](product-setup.png): step 2 of 4, optional warning review and continue with no change.
- [Diagnostics](product-diagnostics.png): expanded controls and sample log.
- [Prior workspace](setup-ux-main.png) and [prior step 2](setup-ux-warning.png) for comparison.
- [Source mockups](../design-references/product-ui.md).

Layout probe: ko/en/ja; Qt scale factors 1.00/1.25/1.50/1.75/2.00; main 390×480 and guide 350×350 logical pixels; no horizontal scroll in the main content or active guide page. Guide navigation remains outside its vertical scroll. Font metrics confirm U+2194 in Windows Qt. This is not a physical monitor matrix or a packaged EXE trial.

No tutorial media was bundled. If Trust navigation remains unclear, use two real static Aseprite captures from a clean test profile rather than reconstructing the approval prompt or adding autoplay.
