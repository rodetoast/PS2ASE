# Pivot Fixer / Ase-PS Bridge Pro v0.3.6

## Summary

v0.3.6 improves Folder -> Frames selection handling for Photoshop folder structures.

## Improvements

- Folder -> Frames now treats directly selected Photoshop subfolders as independent frame containers.
- This means selecting subfolders such as `13`, `Group 9`, `Group 10`, and `Group 8` inside a parent folder such as `Overdrive` creates separate frames for each selected subfolder.
- Selecting both a folder and its child layers no longer duplicates those child layers in the exported metadata.
- If no folder is directly selected, the existing fallback behavior is preserved.

## Compatibility

- Normal mode is unchanged.
- Layer -> Frames mode is unchanged.
- The Folder -> Frames hotfix behavior from v0.3.5 is preserved.

## Notes

- This release does not change the Aseprite paste logic.
- Build artifacts are not included in Git.
