# IPv4 Subnet Calculator and VLSM Planner

Make IP-address calculations and network planning easier to inspect and repeat.

## Implemented work

IPv4 parsing; CIDR and dotted-mask input; network, broadcast, wildcard, and host-range calculations; equal subnet splitting; variable-length subnet planning; Tkinter and terminal interfaces. The calculation logic includes handling for `/31` and `/32` networks.

## Status and limitations

Source implementations for personal networking tools; not evidence of managing a production network.

## Source snapshot

3 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Calculation logic is separated from graphical and terminal interfaces. Integer address arithmetic makes masks and ranges explicit; VLSM allocates different block sizes for different host requirements.
