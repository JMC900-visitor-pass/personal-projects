# Monster Forge and Worldbuilding Tools

Turn creature briefs into structured, saved monster sheets and connected worldbuilding notes.

## Implemented work

Python HTTP backend; Ollama integration; reference retrieval from a bundled monster dataset; schema checks and deterministic calculations; streamed job progress; SQLite bestiary storage; JSON and Obsidian Markdown export. Additional modules scan world notes and coordinate incremental world-content generation.

## Status and limitations

Local AI application. Valid structure does not establish good encounter balance or accurate generated prose. In-progress generation jobs do not survive a server restart, although saved monsters persist.

## Source snapshot

13 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Reference retrieval provides context without model training. Backend checks and deterministic calculations constrain generated records. SQLite stores records while Markdown supports editable linked notes.
