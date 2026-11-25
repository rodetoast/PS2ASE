# Initial setup final polish and manual check

Windows Qt source-window captures, starting from `1243412`. Host and shortcut status in these images is simulated; the Aseprite icon comes from the installed executable.

- [Shortcut preparation with Aseprite running](shortcut-folder.png)
- [Both results shown in the compact completion card](shortcut-complete.png)
- [Warning trade-offs in a 335×440 logical-pixel window at 200%](warning-200.png)

Direct open is available only after the configured Aseprite is verified closed, and it checks again immediately before launching. When running, unknown, or after a failed launch, use the folder. Switching steps ends the current probe and removes its generated PNG. Observations are kept for the same targets until retry or application exit; changing Photoshop clears F4 only, and changing Aseprite clears both.

## Manual verification checklist

Use a spare Windows user or test PC for genuine first-run and Trust checks. Do not reset the production profile, close someone else's host, install over custom bindings, or use a work document. Set aside any clipboard data before deliberately creating a fresh Photoshop copy. Keep only the current Bridge instance open during the test.

1. Launch the latest development source (`bridge_ui.py`) in the test profile. Check language selection, initial setup and the selected Photoshop EXE/path.
2. Review the warning trade-offs. Keep warnings for the default path and approve the test script in Photoshop yourself when prompted. Only test changing the policy in a disposable profile with the selected Photoshop closed; confirm the scope, backup and restart separately.
3. Check Aseprite paths, installed scripts and F4/F5 bindings. Install only if needed and only after checking those bindings. Use a test document and approve the individual scripts through Aseprite's **File > Scripts** Trust flow; do not approve Trust on behalf of another user.
4. Start the shortcut test. For a running host, open the generated PNG in that host from the folder. Click the ready button, then physically press **F5** in the test PNG. Confirm a fresh result appears and that it did not replace the existing Bridge preview/clipboard. A fresh result does not itself prove key input.
5. For **F4**, prepare a Photoshop copy from a small disposable PSD and use only the generated test PNG as the destination. Physically press F4, inspect the cel/layer, then record what you saw. Skip F4 if no suitable Photoshop copy is available.
6. Close the test PNG without saving. Select **Finish and continue**, confirm the independent results on the summary, then close the guide. Reopen it to confirm the same-session observations remain. In two disposable documents, perform fresh regular transfers in both directions after closing the guide, and check Preview and paste.

Installed Aseprite icon extraction was checked read-only; the extracted image differs from Qt's generic file icon. Both hosts were running, so this task did not open or close host documents, change Trust or warnings, or run physical F4/F5. No build, package or operations catalog changes.
