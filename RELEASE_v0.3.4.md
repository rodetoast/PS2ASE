# Pivot Fixer / Ase-PS Bridge Pro v0.3.4

## Release Summary

v0.3.4 adds Photoshop-to-Aseprite frame transfer modes while preserving the existing Normal copy/paste workflow. This release focuses on animation-oriented transfer: selected Photoshop folders or layers can now become sequential Aseprite frames with predictable layer-row reuse.

## Major Features

### 1. Folder -> Frames

- Splits Photoshop content into Aseprite frames by top-level Photoshop folder.
- Supports selecting a folder itself, layers inside a folder, or a combination of folder and child layers.
- Uses the Photoshop layer panel top-to-bottom order, not alphabetical order.
- Pastes from the current Aseprite active frame.
- Places cels starting from the active Aseprite layer row and reuses the same row index across following frames.
- Does not create the top-level Photoshop folder as an Aseprite group.

### 2. Layer -> Frames

- Converts each selected Photoshop pixel layer into one Aseprite frame.
- Uses the current Aseprite active layer as the single target layer row.
- Creates frame-by-frame cels on that same layer row.
- Avoids unnecessary new layer rows.
- Supports selected pixel layers inside Photoshop folders without importing unselected siblings.
- Rejects selected Photoshop folders/groups with a clear error.

### 3. Clipboard Frame Mode Display

- Shows whether the current clipboard payload was copied as Normal, Folder -> Frames, or Layer -> Frames.
- Clarifies that Copy Mode is applied on the next Photoshop copy.
- Prevents confusion when the UI-selected copy mode differs from the already-copied clipboard mode.

### 4. Ground Line Default Alignment

- Migrates the default alignment to Ground Line.
- Keeps user choices after migration if the user later selects Center or Absolute in Settings.
- Alignment remains paste-time behavior, so changing alignment after copy can still affect paste.

### 5. Preview Improvements

- Multi-frame metadata previews only the first frame to avoid stacked-frame preview confusion.
- Frame mode / clipboard mode UI was compacted to keep the preview area stable.

## Fixes And Improvements

- Preserved Normal mode behavior while adding frame-oriented workflows.
- Preserved existing Center, Absolute, and Ground Line alignment behavior.
- Improved messaging around copy-time Frame Mode versus paste-time Alignment.
- Kept Aseprite layer-row reuse predictable for frame-based paste workflows.
- Reduced UI crowding after adding frame mode controls.

## Test Checklist

- Normal Photoshop -> Aseprite copy/paste regression.
- Folder -> Frames:
  - Folder-based frame split.
  - Folder plus selected child layers.
  - Active frame offset.
  - Active layer row reuse.
- Layer -> Frames:
  - Multiple selected Photoshop pixel layers become sequential frames.
  - Active Aseprite layer receives all frame cels.
  - No extra layer rows are created unnecessarily.
  - Selected pixel layers inside Photoshop folders work without importing siblings.
  - Selected folders/groups show a clear error.
- Ground Line default and user override behavior.
- Clipboard mode display for Normal / Folder -> Frames / Layer -> Frames.
- Preview shows only the first frame for multi-frame metadata.
- Aseprite script reinstall flow.

## Known Notes

- Frame Mode is a copy-time setting. Changing the UI mode after copying does not reinterpret the existing clipboard payload.
- Alignment is a paste-time setting. Changing alignment after copying can still update the clipboard payload for paste.
- After Lua script changes, reinstall or force reinstall Aseprite scripts so `%APPDATA%\Aseprite\scripts\aseprite_paste.lua` matches the bundled script.
- First-time users must still approve Aseprite script Trust manually from `File > Scripts`.

## Commits

- `c9034ab` Add folder-to-frames paste mode
- `283de2f` Add Photoshop layer-to-frames mode
