# Crispy Core: Experimental C++ Emulation

Explore an independent interpreter and hardware model behind the native player interface.

## Implemented work

C++20 CPU interpretation and selected memory, display, timer, interrupt, mapper, DMA, and state-persistence functionality; original demonstration ROMs; a C interface to the host application; local checks and recorded external test-suite results.

## Status and limitations

Experimental. Audio and substantial compatibility work remain incomplete. The independent preview is separate from the mGBA-powered application. Recorded checks cover selected behaviours and do not establish full retail-game compatibility.

## Source snapshot

20 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

A C++ core is separated from the host UI through a small interface, allowing headless checks. Selected passing tests demonstrate exercised behaviours rather than complete console compatibility.
