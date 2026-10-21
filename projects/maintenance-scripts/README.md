# Windows Maintenance and Mac-to-Windows Connection Scripts

Put repeatable maintenance and connection-setup steps into scripts.

## Implemented work

PowerShell scripts covering Windows Update service/cache maintenance and network-reset steps; Bash scripts configuring a direct Ethernet connection and generating an RDP configuration file.

## Status and limitations

Administrative script prototypes. Their successful use on target machines was not verified during this review. Network scripts contain machine-specific assumptions.

## Source snapshot

2 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

PowerShell coordinates Windows-native maintenance commands. These scripts require platform-specific permissions and recovery planning; they are not general repair guarantees.
