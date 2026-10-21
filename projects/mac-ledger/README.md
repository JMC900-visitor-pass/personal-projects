# Mac Ledger Filesystem Inventory

Capture filesystem metadata in a form that can be browsed and compared later.

## Implemented work

Scan plans, source exclusions, Markdown directory inventories, access-coverage reporting, metadata-based snapshot comparison, literal queries, and optional environment inventory. The implementation distinguishes confirmed removals from unknown states caused by access failures.

## Status and limitations

Local prototype with tests and a documented scope. It is an inventory tool, not a backup, content-integrity monitor, or security certification system.

## Source snapshot

4 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Markdown supports readable evidence with embedded structured records. Coverage failures remain explicit so unreadable paths are not treated as confirmed deletions. Comparisons use metadata rather than content hashes.
