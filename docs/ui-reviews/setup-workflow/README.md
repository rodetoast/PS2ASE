# Initial setup: connection, safety, and usable checks

Windows Qt/Fusion captures of the development commit that adds this gallery. Host and installation statuses are synthetic; the Photoshop icon is read from the installed 2027 executable. Captures show the client area. The native caption was verified independently using its HWND and DWM.

- [01 Connection and warnings](review-01.png) · [02 Aseprite and final checklist](review-02.png) · [03 Compact warnings at 200%](review-03.png)
- Individual PNGs: [Connection](connection.png) · [Warnings](warning.png) · [Aseprite](aseprite.png) · [Checklist](summary.png) · [Compact](compact-200.png)
- [Previous card design](../setup-cards/README.md)

## Behavior

- The guide is non-modal. Opening it from Settings hides the settings dialog and restores unsaved entries afterward unless the guide changed that particular path. Stage tabs distinguish visit and selection, not completion. Actions and navigation stay outside the scrolling content; the desktop layout is 580×685 logical px with a screen-aware cap.
- Photoshop identity and process state are separate from a tested connection. Warning review is an explicit choice only when the target is verified and no Photoshop process was found. Defaults/kept, preference-file off, live state unknown, and a change made in this session are distinct. The existing consent, closed-host recheck, backup, and restart safeguards still apply.
- Script presence, shortcut registration and Trust records are separate. The guide does not ask for reinstallation when files and bindings match. The guided test creates a disposable PNG; matching fresh Aseprite copy results are observed without publishing to the Bridge clipboard or changing edit history. This proves script output, not which key caused it. F4 uses an existing Photoshop copy only, on the test document, and is recorded as user-observed. Results belong to the current test; late or earlier test results cannot claim the new test. Keep only the updated Bridge instance open while testing.
- Native caption colors follow the launcher DWM implementation where supported; native window controls are retained. Qt appends the product name to the short dialog title once.

## Verification

- Automated coverage: 131 tests. Guide layout and actions were exercised in Korean, English and Japanese using Windows Qt at 100/125/150/175/200%. At desktop size the warning and review content fit without scrolling; at compact size their actions remain visible even when content scrolls.
- Aseprite 1.3.18.6 CLI ran the unchanged copy script on the disposable PNG and produced one fresh job in an isolated Bridge data path. The app observed that result without calling the clipboard publisher. Physical F4/F5, a real Trust dialog interaction, and a new Photoshop transfer were not tested.
- No new build, ZIP, catalog change or publication. Existing 0.3.7-rc1 and operating 0.3.6 artifacts were preserved. Capture script: `tests/render_setup_cards.py`.
