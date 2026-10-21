# GBA Studio Recovery Workspace and REA Launcher

Organise cartridge-analysis projects and make local analysis/model workflows easier to launch and resume.

## Implemented work

Project import and header checks; hash-based identities; resumable instruction-analysis queues; Ollama-generated C drafts; compilation and limited compiler-repair attempts; retained prompts, responses, and diagnostics. The separate REA launcher integrates existing REA/OpenCode tooling and model discovery.

## Status and limitations

Experimental analysis workflow. Compilation does not prove equivalence or a playable native game. The workspace documents one existing Emerald native-port proof of concept based on upstream recovered source. REA and the upstream game projects are external software.

## Source snapshot

6 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Bounded model calls retain instruction evidence and compiler diagnostics. Resumable queues preserve progress. Compilation is kept separate from claims of equivalent behaviour or playable native output.
