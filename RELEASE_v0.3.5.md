# Pivot Fixer / Ase-PS Bridge Pro v0.3.5

## Release Summary

v0.3.5 is a Folder -> Frames hotfix for v0.3.4. It corrects Photoshop layer ordering and prevents copied cels from remaining in rows that should be empty when consecutive frames contain different numbers of layers.

## Fixes

### Folder -> Frames Layer Order

- Preserves the Photoshop layer panel top-to-bottom order when pasting into Aseprite.
- Places the first source layer on the active Aseprite layer and continues downward.
- Keeps the same target row index across subsequent frames.

### Empty Row Handling

- Clears only the target row range used by the current Folder -> Frames paste before creating cels for each target frame.
- Leaves rows empty when a frame contains fewer source layers than the preceding frame.
- Limits clearing to the paste target frames and target layer rows.

### Empty Frame Creation

- Uses empty frames when Folder -> Frames needs to extend the Aseprite timeline.
- Prevents newly created frames from inheriting cels from the preceding frame.

## Preserved Behavior

- The active Aseprite layer remains the first target row, with additional rows placed below it.
- Normal mode is unchanged.
- Layer -> Frames mode is unchanged.
- Photoshop copy metadata generation is unchanged.
- All existing v0.3.4 features remain available.

## Update Note

- On startup, the Bridge app compares its bundled Aseprite scripts with the installed copies and automatically updates files that are missing or different.
- Aseprite script Trust approval is still required only once and is not shown again for users who already confirmed it.
- If script installation still fails, use the Aseprite script/shortcut force reinstall option in Settings.
- The latest `aseprite_paste.lua` must be present at `%APPDATA%\Aseprite\scripts\aseprite_paste.lua` before testing the hotfix.

## Test Checklist

- Folder -> Frames preserves Photoshop top-to-bottom layer order.
- The active Aseprite layer is used as row 1 and following rows are placed below it.
- Frames with fewer source layers leave unused target rows empty.
- Multiple Folder -> Frames frames reuse matching target rows.
- Normal mode regression test.
- Layer -> Frames regression test.
- Existing-user bundled script auto-update without repeating Trust onboarding.
- Aseprite script force reinstall verification.
