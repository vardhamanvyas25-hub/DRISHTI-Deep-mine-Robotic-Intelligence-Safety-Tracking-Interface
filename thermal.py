import time

import cv2
import numpy as np


def get_thermal_data(scenario="SAFE"):
    rows = 24
    cols = 32

    frame = np.random.normal(
        loc=27.5,
        scale=0.35,
        size=(rows, cols)
    ).astype(np.float32)

    show_hotspot = (
        scenario in {"GAS_LEAK", "TILT_DANGER", "WATER_LEAK"}
        or int(time.time()) % 14 in range(7, 12)
    )

    if show_hotspot:
        center_x = 22
        center_y = 12

        peak_temperature = 52.0 if scenario == "GAS_LEAK" else 42.0

        for y in range(rows):
            for x in range(cols):
                radius = (
                    (x - center_x) ** 2
                    + (y - center_y) ** 2
                ) ** 0.5

                if radius < 6:
                    frame[y, x] += max(
                        0,
                        peak_temperature - 27.5 - radius * 4.0
                    )

    max_temp = float(frame.max())
    avg_temp = float(frame.mean())

    hot_points = np.argwhere(frame > avg_temp + 4.0)

    hotspot = "NONE"

    if len(hot_points) > 0:
        y, x = hot_points.mean(axis=0)

        if x < cols / 3:
            horizontal = "LEFT"
        elif x > 2 * cols / 3:
            horizontal = "RIGHT"
        else:
            horizontal = "CENTRE"

        if y < rows / 3:
            vertical = "TOP"
        elif y > 2 * rows / 3:
            vertical = "BOTTOM"
        else:
            vertical = "MIDDLE"

        hotspot = f"{vertical}-{horizontal}"

    normalized = cv2.normalize(
        frame,
        None,
        0,
        255,
        cv2.NORM_MINMAX
    ).astype(np.uint8)

    enlarged = cv2.resize(
        normalized,
        (640, 480),
        interpolation=cv2.INTER_CUBIC
    )

    heatmap = cv2.applyColorMap(
        enlarged,
        cv2.COLORMAP_INFERNO
    )

    return {
        "image": heatmap,
        "max_temp_c": round(max_temp, 1),
        "avg_temp_c": round(avg_temp, 1),
        "hotspot": hotspot,
        "hot_pixels": int(len(hot_points))
    }