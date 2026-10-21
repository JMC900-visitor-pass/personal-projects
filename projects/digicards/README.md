# Digicards Card-Game Workbench

Combine card creation, deck building, and local practice battles.

## Implemented work

Card validation; legal deck construction; seeded battle transitions; an opponent selecting legal actions; manual and Ollama-assisted creation; ComfyUI image-generation integration; local persistence.

## Status and limitations

Local authoring and practice prototype. Public multiplayer and a server-authoritative competitive game are not implemented.

## Source snapshot

12 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Shared JavaScript rules support browser/server validation. Battle actions operate on cloned state. Ollama generates structured card drafts and ComfyUI executes image workflows; neither output is treated as executable game code.
