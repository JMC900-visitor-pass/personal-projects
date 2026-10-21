# Toner Desk and Toner Request System

Give staff a simple way to request printer consumables and give ICT a structured queue to manage.

## Implemented work

Browser request forms; room, printer, and toner records; request status management; administration routes; SQL persistence; email integration. The MySQL/MariaDB version also includes report and CSV-export routes. Deployment documentation covers Ubuntu, Apache reverse proxying, and service setup.

## Status and limitations

Local application implementations with deployment instructions. Actual workplace deployment and adoption are not established by this review. Treat the two folders as related approaches to one problem.

## Source snapshot

16 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Node.js and Express fit a form/API workflow. SQL represents related request, room, printer, and toner records. The SQLite variant reduces database setup; the MySQL/MariaDB variant uses a separately managed database. Authentication differs between variants and requires deployment-specific review.
