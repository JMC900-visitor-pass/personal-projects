"""
Room Point Tracker - detects and tracks moving objects via webcam.
Shows bounding boxes and center dots with persistent IDs.
Press Q to quit, R to reset background, Space to pause.
"""

import cv2
import numpy as np
from collections import OrderedDict
from scipy.spatial import distance as dist


class CentroidTracker:
    """Assigns persistent IDs to detected objects by matching centroids frame-to-frame."""

    def __init__(self, max_disappeared=30):
        self.next_id = 0
        self.objects = OrderedDict()      # id -> centroid
        self.disappeared = OrderedDict()  # id -> frames missing
        self.max_disappeared = max_disappeared

    def register(self, centroid):
        self.objects[self.next_id] = centroid
        self.disappeared[self.next_id] = 0
        self.next_id += 1

    def deregister(self, obj_id):
        del self.objects[obj_id]
        del self.disappeared[obj_id]

    def update(self, rects):
        if len(rects) == 0:
            for obj_id in list(self.disappeared):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self.deregister(obj_id)
            return self.objects

        input_centroids = np.array([
            ((x + x2) // 2, (y + y2) // 2)
            for (x, y, x2, y2) in rects
        ], dtype="int")

        if len(self.objects) == 0:
            for c in input_centroids:
                self.register(c)
        else:
            obj_ids = list(self.objects.keys())
            obj_centroids = list(self.objects.values())

            D = dist.cdist(np.array(obj_centroids), input_centroids)
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows, used_cols = set(), set()
            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue
                if D[row, col] > 120:   # max jump distance in pixels
                    continue
                obj_id = obj_ids[row]
                self.objects[obj_id] = input_centroids[col]
                self.disappeared[obj_id] = 0
                used_rows.add(row)
                used_cols.add(col)

            unused_rows = set(range(D.shape[0])) - used_rows
            unused_cols = set(range(D.shape[1])) - used_cols

            for row in unused_rows:
                self.disappeared[obj_ids[row]] += 1
                if self.disappeared[obj_ids[row]] > self.max_disappeared:
                    self.deregister(obj_ids[row])

            for col in unused_cols:
                self.register(input_centroids[col])

        return self.objects


# Assign a unique color per object ID
def id_color(obj_id):
    palette = [
        (0, 255, 100), (0, 180, 255), (255, 80, 0),
        (255, 0, 200), (200, 255, 0), (0, 255, 255),
        (255, 200, 0), (180, 0, 255),
    ]
    return palette[obj_id % len(palette)]


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    bg_subtractor = cv2.createBackgroundSubtractorMOG2(
        history=300, varThreshold=50, detectShadows=True
    )

    tracker = CentroidTracker(max_disappeared=25)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    paused = False
    trail_points = {}  # id -> list of centroids for trail drawing
    TRAIL_LEN = 40
    MIN_AREA = 1200    # ignore tiny noise blobs

    print("Controls: Q = quit | R = reset background | Space = pause")

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=300, varThreshold=50, detectShadows=True
            )
            tracker = CentroidTracker(max_disappeared=25)
            trail_points.clear()
            print("Background reset.")
        elif key == ord(' '):
            paused = not paused

        if paused:
            continue

        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)          # mirror so it feels natural
        display = frame.copy()
        h, w = frame.shape[:2]

        # --- Motion mask ---
        fg_mask = bg_subtractor.apply(frame)
        fg_mask[fg_mask == 127] = 0         # remove shadows (value 127)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=2)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_DILATE, kernel, iterations=3)

        # --- Find contours ---
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        rects = []
        for cnt in contours:
            if cv2.contourArea(cnt) < MIN_AREA:
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            # Ignore boxes that fill nearly the whole frame (background reset glitch)
            if cw > w * 0.9 and ch > h * 0.9:
                continue
            rects.append((x, y, x + cw, y + ch))

        # --- Update tracker ---
        objects = tracker.update(rects)

        # --- Draw trails ---
        for obj_id, centroid in objects.items():
            if obj_id not in trail_points:
                trail_points[obj_id] = []
            trail_points[obj_id].append(tuple(centroid))
            if len(trail_points[obj_id]) > TRAIL_LEN:
                trail_points[obj_id].pop(0)

        # Remove trails for gone objects
        gone = set(trail_points) - set(objects)
        for gid in gone:
            del trail_points[gid]

        for obj_id, pts in trail_points.items():
            color = id_color(obj_id)
            for i in range(1, len(pts)):
                alpha = i / len(pts)
                faded = tuple(int(c * alpha) for c in color)
                cv2.line(display, pts[i - 1], pts[i], faded, 2)

        # --- Draw boxes & dots ---
        for (x, y, x2, y2) in rects:
            cv2.rectangle(display, (x, y), (x2, y2), (200, 200, 200), 1)

        for obj_id, centroid in objects.items():
            cx, cy = centroid
            color = id_color(obj_id)

            # Outer glow ring
            cv2.circle(display, (cx, cy), 14, color, 2)
            # Solid center dot
            cv2.circle(display, (cx, cy), 6, color, -1)

            # Label
            label = f"#{obj_id}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(display, (cx - 4, cy - lh - 20), (cx + lw + 4, cy - 10), color, -1)
            cv2.putText(display, label, (cx, cy - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

        # --- HUD ---
        hud = f"Tracking: {len(objects)}  |  Q=quit  R=reset  Space=pause"
        if paused:
            hud += "  [PAUSED]"
        cv2.putText(display, hud, (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Small mask thumbnail in corner
        mask_small = cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR)
        mask_small = cv2.resize(mask_small, (w // 5, h // 5))
        display[10:10 + mask_small.shape[0], 10:10 + mask_small.shape[1]] = mask_small
        cv2.putText(display, "motion mask", (10, 10 + mask_small.shape[0] + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

        cv2.imshow("Room Tracker", display)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install opencv-python scipy numpy")
