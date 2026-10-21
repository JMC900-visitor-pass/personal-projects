# Raidforge Tactical Scenario Generator

Generate tabletop scenarios with connected maps, monster cards, and consistent rules.

## Implemented work

Seeded room generation; role-based monsters; party/difficulty threat budgets; offline or Ollama-generated narrative; packet validation; reachability checks; a browser interface and saved scenario records.

## Status and limitations

Tabletop scenario-generation prototype. Balance remains provisional; this is not a complete digital tactical game. Archived versions are grouped with the current project. Some README references to agent entry points need reconciling with the current file layout before those features are claimed separately.

## Source snapshot

25 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Code owns encounter arithmetic and seeded map generation. Optional model calls supply narrative. Packet and reachability checks validate structure without proving game balance.
