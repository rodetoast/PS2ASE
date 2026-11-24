# Copied-layer editing controls

Windows Qt/Fusion source-widget captures in an isolated test profile, using a synthetic three-layer preview. These captures belong to the implementation commit that adds this page. They are not a packaged EXE run or host-transfer evidence.

- [Before: icon-only editor](dark-workspace.png)
- [After: workspace with copied layers](copied-layer-editing.png)
- [After: 390×480 logical-pixel window at Qt scale 200%](copied-layer-editing-narrow-200.png)

“복사 레이어 편집” / “Edit Copied Layers” names the data being edited, not just the preview display. Flip and rotate controls sit directly below the preview; undo and redo have their own row. All five actions show their names without hover and retain accessible names. The empty-state text stays unchanged to avoid adding noise or shifting the preview. Segments keep their radio semantics and distinguish selection, focus, hover, press and disabled states visually.

Focused offscreen suite: 25 tests (preview layout and mocked job lifecycle). Windows Qt layout and text fit: ko/en/ja, scale 100/125/150/175/200%, 390×480 logical pixels; no horizontal scroll, all five edit controls visible before scrolling, and minimum button height 34 logical pixels. This is Qt scaling, not a physical monitor matrix. No Windows Use, Photoshop/Aseprite transfer, or new build/package.
