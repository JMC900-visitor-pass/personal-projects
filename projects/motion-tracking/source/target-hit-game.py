"""
Target Hit Game - use motion detection to hit square targets on screen.
Track your hand/body and move it over targets to hit them.
Press Q to quit, R to reset score, Space to pause.
"""

import cv2
import numpy as np
import random
from collections import deque

TARGET_SIZE = 80
HIT_DISTANCE = 60            # max centroid distance for a hit
MIN_AREA = 800
MAX_AREA = 150000            # ignore huge blobs (whole-frame glitches)
KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
COLORS = [
    (0, 255, 100), (0, 180, 255), (255, 80, 0),
    (255, 0, 200), (200, 255, 0), (255, 0, 100),
    (0, 200, 255), (255, 200, 0), (180, 0, 255),
]
CURSOR_RADIUS = 12
SMOOTHING = 8                # frames for centroid smoothing


class Target:
    """A square target that spawns at a random position."""

    def __init__(self, x, y, size=TARGET_SIZE):
        self.x = x
        self.y = y
        self.size = size
        self.alive = True
        self.color = random.choice(COLORS)
        self.pulse = random.uniform(0, 6.28)

    def rect(self):
        return (self.x, self.y, self.x + self.size, self.y + self.size)

    def center(self):
        return (self.x + self.size // 2, self.y + self.size // 2)

    def hit(self):
        self.alive = False

    def draw(self, img, cursor_pos=None):
        x, y, x2, y2 = self.rect()
        self.pulse += 0.1
        pulse_scale = 1 + 0.08 * np.sin(self.pulse)

        # Glow effect
        glow = int(self.size * 0.35 * pulse_scale)
        cv2.rectangle(img, (x - glow, y - glow), (x2 + glow, y2 + glow),
                       (0, 0, 0), 4)
        cv2.rectangle(img, (x - glow, y - glow), (x2 + glow, y2 + glow),
                      self.color, 2)

        # Main box
        cv2.rectangle(img, (x, y), (x2, y2), self.color, -1)

        # Inner crosshair
        cx, cy = self.center()
        s = self.size // 4
        cv2.line(img, (cx - s, cy), (cx + s, cy), (0, 0, 0), 2)
        cv2.line(img, (cx, cy - s), (cx, cy + s), (0, 0, 0), 2)

        # Border
        cv2.rectangle(img, (x, y), (x2, y2), (255, 255, 255), 2)

        # Distance indicator line (from target to cursor)
        if cursor_pos is not None:
            ccx, ccy = cursor_pos
            cv2.line(img, (cx, cy), (ccx, ccy), (255, 255, 255), 1)
            dist = int(np.sqrt((cx - ccx) ** 2 + (cy - ccy) ** 2))
            cv2.putText(img, f"{dist}px", (cx + 10, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)


def spawn_target(w, h):
    margin = TARGET_SIZE + 40
    x = random.randint(margin, w - margin - TARGET_SIZE)
    y = random.randint(80, h - margin - TARGET_SIZE)
    return Target(x, y)


def get_largest_motion_centroid(fg_mask, min_area=MIN_AREA, max_area=MAX_AREA):
    """Find the largest motion blob and return its centroid and bounding rect."""
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_cnt = None
    best_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        if area > best_area:
            best_area = area
            best_cnt = cnt

    if best_cnt is None:
        return None, None

    x, y, cw, ch = cv2.boundingRect(best_cnt)
    centroid = (x + cw // 2, y + ch // 2)
    rect = (x, y, x + cw, y + ch)
    return centroid, rect


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

    score = 0
    combo = 0
    max_combo = 0
    total_hits = 0
    total_misses = 0
    targets = []
    active_target = None
    paused = False
    hit_effects = []            # list of (x, y, color, life)
    hit_cooldown = 0            # frames before next hit is possible

    # Body tracking state
    raw_cursor = (640, 360)     # start at center
    smoothed_cursor = (640, 360)
    cursor_active = False       # True when body is being tracked
    tracking_history = deque(maxlen=SMOOTHING)

    print("Controls: Q = quit | R = reset | Space = pause")
    print("Move your hand/body in front of camera to hit targets!")
    print("The cursor follows your largest motion blob.")

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            score = 0
            combo = 0
            max_combo = 0
            total_hits = 0
            total_misses = 0
            targets.clear()
            hit_effects.clear()
            active_target = None
            hit_cooldown = 0
            print("Score reset.")
        elif key == ord(' '):
            paused = not paused

        if paused:
            continue

        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        display = frame.copy()
        h, w = frame.shape[:2]

        # --- Spawn first target if none ---
        if not active_target or not active_target.alive:
            active_target = spawn_target(w, h)

        # --- Motion detection ---
        fg_mask = bg_subtractor.apply(frame)
        fg_mask[fg_mask == 127] = 0
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, KERNEL, iterations=2)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_DILATE, KERNEL, iterations=3)

        # --- Get tracked body position ---
        raw_cursor, cursor_rect = get_largest_motion_centroid(fg_mask)

        if raw_cursor is not None:
            cursor_active = True
            tracking_history.append(raw_cursor)
            avg_x = sum(p[0] for p in tracking_history) / len(tracking_history)
            avg_y = sum(p[1] for p in tracking_history) / len(tracking_history)
            smoothed_cursor = (int(avg_x), int(avg_y))
        else:
            cursor_active = False
            if len(tracking_history) > 0:
                tracking_history.clear()

        # --- Check collision with active target ---
        if active_target and active_target.alive:
            tcx, tcy = active_target.center()
            ccx, ccy = smoothed_cursor
            dist = np.sqrt((tcx - ccx) ** 2 + (tcy - ccy) ** 2)

            if dist < HIT_DISTANCE:
                if hit_cooldown <= 0:
                    # Successful hit
                    total_hits += 1
                    combo += 1
                    if combo > max_combo:
                        max_combo = combo
                    score += 10 * combo
                    hit_cooldown = 15      # 15-frame cooldown between hits

                    # Hit effect at target center
                    hit_effects.append((tcx, tcy, active_target.color, 25))
                    active_target.hit()

                    print(f"Hit! Score: {score}  Combo: x{combo}")
                else:
                    # Too soon - miss
                    total_misses += 1
                    combo = 0
                    print(f"Miss! Cooldown active. Combo reset.")

        if hit_cooldown > 0:
            hit_cooldown -= 1

        # --- Draw hit effects ---
        new_effects = []
        for ex, ey, ecolor, life in hit_effects:
            alpha = life / 25.0
            radius = int(35 * (1 - alpha) + 10)
            thickness = max(1, int(4 * alpha))
            cv2.circle(display, (ex, ey), radius, ecolor, thickness)
            cv2.circle(display, (ex, ey), radius // 2, (255, 255, 255), max(1, int(2 * alpha)))
            if life > 1:
                new_effects.append((ex, ey, ecolor, life - 1))
        hit_effects = new_effects

        # --- Draw active target ---
        if active_target and active_target.alive:
            active_target.draw(display, smoothed_cursor if cursor_active else None)

        # --- Draw cursor (tracked body position) ---
        cx, cy = smoothed_cursor
        if cursor_active:
            # Outer ring
            cv2.circle(display, (cx, cy), CURSOR_RADIUS + 6, (0, 0, 0), 2)
            # Main ring
            cv2.circle(display, (cx, cy), CURSOR_RADIUS, (255, 255, 255), 2)
            # Center dot
            cv2.circle(display, (cx, cy), 4, (255, 255, 255), -1)

            # Draw bounding box of tracked body
            if cursor_rect:
                x, y, x2, y2 = cursor_rect
                cv2.rectangle(display, (x, y), (x2, y2), (255, 255, 0), 1)
        else:
            # Faded cursor when not tracking
            cv2.circle(display, (cx, cy), CURSOR_RADIUS, (100, 100, 100), 1)

        # --- Draw connection line from cursor to target ---
        if active_target and active_target.alive and cursor_active:
            tcx, tcy = active_target.center()
            ccx, ccy = smoothed_cursor
            dist = int(np.sqrt((tcx - ccx) ** 2 + (tcy - ccy) ** 2))

            # Proximity indicator on cursor
            if dist < HIT_DISTANCE:
                # Pulsing green glow = ready to hit
                pulse = int(8 + 4 * np.sin(cv2.getTickCount() * 0.01))
                cv2.circle(display, (cx, cy), CURSOR_RADIUS + pulse, (0, 255, 0), 2)

        # --- HUD ---
        hud_y = 30
        hud_lines = [
            f"Score: {score}",
            f"Combo: x{combo}",
            f"Max Combo: x{max_combo}",
        ]
        if paused:
            hud_lines.append("[PAUSED]")

        for line in hud_lines:
            cv2.putText(display, line, (15, hud_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            hud_y += 28

        # Connection rate stats
        total_attempts = total_hits + total_misses
        if total_attempts > 0:
            rate = int(total_hits / total_attempts * 100)
        else:
            rate = 0
        stats_y = hud_y + 10
        cv2.putText(display, f"Hits: {total_hits}/{total_attempts} ({rate}%)",
                      (15, stats_y),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Combo display with fire emoji
        if combo >= 3:
            combo_text = f"{''.join(['\U0001f525'] * min(combo, 5))} x{combo}"
            combo_color = (255, 100, 0) if combo >= 5 else (255, 200, 0)
            cv2.putText(display, combo_text, (w // 2 - 80, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, combo_color, 2)

        # Cooldown indicator
        if hit_cooldown > 0:
            cv2.putText(display, "COOLDOWN", (w // 2 - 45, h - 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 100), 2)

        # Motion mask thumbnail
        mask_small = cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR)
        mask_small = cv2.resize(mask_small, (w // 6, h // 6))
        mask_x = w - mask_small.shape[1] - 10
        mask_y = h - mask_small.shape[0] - 10
        display[mask_y:mask_y + mask_small.shape[0], mask_x:mask_x + mask_small.shape[1]] = mask_small
        cv2.putText(display, "motion", (mask_x, mask_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

        cv2.imshow("Target Hit Game", display)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install opencv-python numpy")
