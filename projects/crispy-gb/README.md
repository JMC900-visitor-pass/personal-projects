# Crispy GB and mGBA Studio

Provide a native macOS library and player for GB, GBC, and GBA games.

## Implemented work

Native Swift/AppKit interface; Metal display; game imports and metadata; display adjustments; pause overlay; keyboard/controller settings; battery saves, save slots, and recovery; standalone Mac application export with upstream notices and source.

## Status and limitations

Native application built around the existing mGBA core. This is integration and frontend work, not authorship of mGBA. Documentation records remaining physical-display, controller, and longer-session checks.

## Source snapshot

25 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

The native UI and Metal renderer integrate an existing emulator core. Host preferences, saves, and recovery are separated from application bundles. The upstream core is not included in this snapshot.
