# Tile-Map Editor

Author maps and gameplay metadata for pixel-art RPGs.

## Implemented work

Tileset import; single-tile and multi-tile painting; eraser, fill, and eyedropper tools; layer management; collision painting; object properties; undo/redo; camera controls; JSON saving and export.

## Status and limitations

Desktop editor implementation. Packaging instructions exist; no fresh package build was performed for this review.

## Source snapshot

22 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Canvas draws the tile grid and editing overlays; Electron provides a desktop shell. Collision, objects, and artwork are stored as distinct concepts. Undo groups editing operations.
