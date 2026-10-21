# Webcam Tracking and Motion-Controlled Target Game

Experiment with turning live camera motion into tracked objects and interaction.

## Implemented work

OpenCV background subtraction; contour-based motion detection; centroid association with persistent IDs; bounding boxes; smoothed motion cursor; targets, scoring, and feedback.

## Status and limitations

Computer-vision prototypes. Centroid tracking is not person identification, and the code does not establish trained object recognition or reliable tracking in all environments.

## Source snapshot

2 selected text source files are included. These are portfolio snapshots, not a guaranteed complete runnable distribution. Personal notes, original documentation, local databases, saves, credentials, generated content, binaries, and artwork are excluded. Local user paths and non-example email addresses are replaced in the copies. Runtime defaults may therefore need configuration.

External libraries, models, datasets, and upstream projects remain credited to their authors. No blanket license or claim of sole authorship is made for this collection.

## Architecture and design decisions

Centroid matching associates nearby motion detections without a trained recognition model. Smoothing reduces cursor jitter; overlap and occlusion remain limitations.
