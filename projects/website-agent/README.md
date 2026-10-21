# Loop Website-Generation Workspace

Generate and revise standalone websites through a builder/reviewer workflow.

## Implemented work

React/Vinext workspace; model API connection; bounded specialist requests and revision passes; code editing; desktop/mobile previews; version restoration; standalone HTML export.

## Status and limitations

Prototype for frontend generation. The documented reviewer examines source; it does not perform real browser testing. Session work is held in memory, and generated backends/deployment are outside scope.

## Source snapshot

10 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

The workspace separates generation and source-review passes and bounds iterations. Exported sites use standalone HTML/CSS/JavaScript. Source review is not browser testing.
