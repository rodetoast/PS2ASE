# Initial setup guide cards

Windows Qt/Fusion captures of the development commit that adds this gallery. The profile, target detection result and process state are synthetic. The Windows icon provider reads the locally installed Photoshop 2027 EXE icon; the app falls back to a neutral application icon when extraction cannot produce a usable icon.

- [Native-resolution review 01: Connection and 200% compact view](review-01.png)
- [Native-resolution review 02: Script warnings and summary](review-02.png)
- Original PNGs: [Connection](connection.png) · [Compact at 200%](compact-200.png) · [Warning](warning.png) · [Summary](summary.png)

Product name, shortened version, full-build tooltip, EXE path and process state now have separate fields. The runtime badge describes the selected EXE, with a separate caution if a different Photoshop is running. Warning and summary pages distinguish configured warnings from live approval; Aseprite file, shortcut, Trust and user-reported runtime status are separate.

The text can wrap within the scrollable page while the step controls remain outside it. Verified at 330×330 logical px in ko/en/ja, with Windows Qt factors 100/125/150/175/200%. The captures came from an isolated test profile. No host transfer, security-setting change, or packaging was performed. Use `tests/render_setup_cards.py` to reproduce the captures.
