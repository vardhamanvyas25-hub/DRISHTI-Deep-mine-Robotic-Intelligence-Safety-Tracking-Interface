import os
import cv2
import time
import math
import threading
import numpy as np

# Try importing hardware libraries for MLX90640 on Raspberry Pi
try:
    import board
    import busio
    import adafruit_mlx90640
    MLX_HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError, ModuleNotFoundError):
    MLX_HARDWARE_AVAILABLE = False

# Try importing YOLOv8
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

class CameraStreamer:
    def __init__(self, remote_webcam_url="http://192.168.50.2:5000//video_feed",
                       remote_thermal_url="http://192.168.50.2:5000//thermal_feed"):
        self.lock = threading.Lock()
        self.latest_detections = []
        self.thermal_stats = {
            "max_temp": 28.5,
            "min_temp": 24.2,
            "avg_temp": 26.8,
            "hotspot": "NONE"
        }
        self.colormap_mode = "INFERNO"  # "INFERNO" or "JET"
        self.enable_yolo = True
        self.running = True

        # Remote stream endpoints
        self.remote_webcam_url = remote_webcam_url
        self.remote_thermal_url = remote_thermal_url
        self.latest_raw_frame = None
        self.remote_stream_active = False

        # 1. Initialize YOLOv8 Model
        self.yolo_model = None
        if YOLO_AVAILABLE:
            model_paths = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yolov8n.pt'),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'drishti_command_centre', 'yolov8n.pt'),
                'yolov8n.pt'
            ]
            for mp in model_paths:
                if os.path.exists(mp):
                    try:
                        print(f"[CAMERAS] Loading YOLOv8 model from {mp} for human and object detection...")
                        self.yolo_model = YOLO(mp)
                        print("[CAMERAS] YOLOv8 loaded successfully.")
                        break
                    except Exception as e:
                        print(f"[CAMERAS] YOLO load error ({mp}): {e}")

        # 2. Local fallback webcam
        self.webcam = None
        self.webcam_connected = False

        # 3. Start Background Thread for Remote Rover Video Stream Grabber
        self.grabber_thread = threading.Thread(target=self._stream_grabber_loop, daemon=True)
        self.grabber_thread.start()

        # 4. Initialize MLX90640 Thermal Sensor
        self.mlx_available = False
        if MLX_HARDWARE_AVAILABLE:
            try:
                i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
                self.mlx = adafruit_mlx90640.MLX90640(i2c)
                self.mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_8_HZ
                self.mlx_available = True
                print("[CAMERAS] MLX90640 Thermal Camera Connected Successfully!")
            except Exception as e:
                print(f"[CAMERAS] MLX90640 hardware not detected ({e}). Using tactical thermal simulation.")
        else:
            print("[CAMERAS] MLX90640 running in tactical thermal simulation mode.")

        # Animation states for simulation fallback
        self._sim_tick = 0.0

    def _stream_grabber_loop(self):
        """Continuously pulls fresh frames from http://192.168.50.2:5000//video_feed with auto-reconnect."""
        while self.running:
            cap = None
            try:
                print(f"[CAMERAS] Connecting to remote web camera at {self.remote_webcam_url}...")
                cap = cv2.VideoCapture(self.remote_webcam_url)
                if cap.isOpened():
                    print("[CAMERAS] Connected to rover stream! Running YOLO human and object detection...")
                    with self.lock:
                        self.remote_stream_active = True

                    while self.running:
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            with self.lock:
                                self.latest_raw_frame = frame
                                self.remote_stream_active = True
                            time.sleep(0.015)
                        else:
                            print("[CAMERAS] Remote video stream paused or dropped, reconnecting...")
                            with self.lock:
                                self.remote_stream_active = False
                            break
                else:
                    with self.lock:
                        self.remote_stream_active = False
                    time.sleep(2.0)
            except Exception as e:
                print(f"[CAMERAS] Remote stream capture error: {e}")
                with self.lock:
                    self.remote_stream_active = False
                time.sleep(2.0)
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

    def _init_local_webcam(self):
        """Fallback to local physical webcam if remote stream is unavailable."""
        if self.webcam is not None:
            try:
                self.webcam.release()
            except Exception:
                pass
            self.webcam = None

        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if os.name == 'nt' else [cv2.CAP_ANY]
        for idx in range(3):
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(idx, backend)
                    if cap.isOpened():
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                            self.webcam = cap
                            self.webcam_connected = True
                            return
                        cap.release()
                except Exception:
                    pass
        self.webcam_connected = False

    def set_colormap(self, mode):
        """Sets thermal colormap to 'INFERNO' or 'JET'."""
        self.colormap_mode = mode.upper()

    def _generate_simulated_optical_frame(self):
        """Creates a realistic tactical rover HUD feed when no physical camera is plugged in."""
        self._sim_tick += 0.05
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        horizon_y = 200
        vanish_x = 320
        grid_color = (40, 60, 80)
        hud_cyan = (255, 235, 0)
        hud_emerald = (80, 220, 100)

        # Background gradient
        for y in range(480):
            factor = (y / 480.0) ** 1.5
            frame[y, :] = (int(10 + factor * 25), int(15 + factor * 30), int(20 + factor * 40))

        # Tunnel perspective lines
        for x_offset in range(-320, 321, 64):
            cv2.line(frame, (vanish_x, horizon_y), (vanish_x + x_offset * 3, 480), grid_color, 1)

        # Scrolling floor grid rungs
        scroll_speed = (self._sim_tick * 40) % 70
        for depth_step in range(1, 8):
            y_pos = int(horizon_y + (depth_step * 38 + scroll_speed) ** 1.1)
            if horizon_y < y_pos < 480:
                width = int(60 + (y_pos - horizon_y) * 2.2)
                cv2.line(frame, (vanish_x - width, y_pos), (vanish_x + width, y_pos), (35, 50, 70), 1)

        # Simulated obstacle / explorer target
        target_dist = 3.5 + 0.8 * math.sin(self._sim_tick * 0.4)
        target_scale = max(0.4, min(1.2, 5.0 / target_dist))
        tw = int(70 * target_scale)
        th = int(120 * target_scale)
        tx = int(320 + 80 * math.sin(self._sim_tick * 0.3) - tw // 2)
        ty = int(horizon_y + 40 * target_scale)

        cv2.rectangle(frame, (tx, ty), (tx + tw, ty + th), (50, 70, 95), -1)
        cv2.circle(frame, (tx + tw // 2, ty + int(th * 0.25)), int(tw * 0.35), (60, 80, 110), -1)
        cv2.putText(frame, "SIMULATED TARGET", (tx - 10, ty - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, hud_cyan, 1)

        # Optical HUD Overlays
        cv2.drawMarker(frame, (320, 240), hud_cyan, cv2.MARKER_CROSS, 28, 1)
        cv2.circle(frame, (320, 240), 40, hud_cyan, 1)

        # Heading Compass Bar
        cv2.rectangle(frame, (180, 10), (460, 32), (15, 25, 35), -1)
        cv2.rectangle(frame, (180, 10), (460, 32), (60, 80, 100), 1)
        heading_deg = int((self._sim_tick * 15) % 360)
        cv2.putText(frame, f"HDG: {heading_deg:03d} DEG [NW]", (245, 26), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, hud_cyan, 1)

        # Bottom Telemetry HUD
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"DRISHTI OPTICAL HUD | {ts}", (15, 465), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 180, 200), 1)
        cv2.putText(frame, "RECONNECTING 192.168.50.2...", (400, 465), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 165, 255), 1)

        self._draw_tactical_brackets(frame, 640, 480, hud_cyan)
        return frame

    def _draw_tactical_brackets(self, img, w, h, color):
        """Draws sci-fi tactical viewfinder corner brackets."""
        b_len = 24
        pad = 12
        cv2.line(img, (pad, pad), (pad + b_len, pad), color, 2)
        cv2.line(img, (pad, pad), (pad, pad + b_len), color, 2)
        cv2.line(img, (w - pad, pad), (w - pad - b_len, pad), color, 2)
        cv2.line(img, (w - pad, pad), (w - pad, pad + b_len), color, 2)
        cv2.line(img, (pad, h - pad), (pad + b_len, h - pad), color, 2)
        cv2.line(img, (pad, h - pad), (pad, h - pad - b_len), color, 2)
        cv2.line(img, (w - pad, h - pad), (w - pad - b_len, h - pad), color, 2)
        cv2.line(img, (w - pad, h - pad), (w - pad, h - pad - b_len), color, 2)

    def generate_webcam_frames(self):
        """Yields MJPEG stream of http://192.168.50.2:5000//video_feed with live YOLOv8 human & object detection."""
        while self.running:
            raw_frame = None
            is_remote = False

            with self.lock:
                if self.latest_raw_frame is not None and self.remote_stream_active:
                    raw_frame = self.latest_raw_frame.copy()
                    is_remote = True

            # If remote stream is not ready, try local webcam
            if raw_frame is None and self.webcam_connected and self.webcam is not None:
                ret, cap_frame = self.webcam.read()
                if ret and cap_frame is not None:
                    raw_frame = cap_frame

            # If still None, generate high-tech simulated tactical reconnaissance frame
            if raw_frame is None:
                frame = self._generate_simulated_optical_frame()
                is_simulation = True
            else:
                frame = raw_frame
                is_simulation = False

            # --- RUN YOLOv8 INFERENCE (Detect Humans & Objects) ---
            detections = []
            if self.enable_yolo and self.yolo_model is not None:
                try:
                    # Run YOLOv8 nano model (detects person, car, phone, bottle, backpack, etc.)
                    results = self.yolo_model(frame, conf=0.35, verbose=False)[0]
                    # Plot bounding boxes directly onto frame with labels & confidence
                    frame = results.plot()

                    for box in results.boxes:
                        cls_id = int(box.cls[0])
                        label = self.yolo_model.names[cls_id]
                        conf = round(float(box.conf[0]), 2)
                        detections.append({
                            "class": label,
                            "confidence": conf,
                            "is_human": (label.lower() == "person")
                        })
                except Exception as e:
                    pass

            with self.lock:
                self.latest_detections = detections

            # Overlay tactical HUD telemetry on frame
            if is_remote:
                cv2.putText(frame, "CAM 01 // LIVE ROVER (192.168.50.2) [YOLOv8 ACTIVE]", (15, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 242, 254), 1, cv2.LINE_AA)
            elif is_simulation:
                cv2.putText(frame, "CAM 01 // SCANNING ROVER STREAM (192.168.50.2)...", (15, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1, cv2.LINE_AA)

            # Draw target count badge
            human_count = sum(1 for d in detections if d.get("is_human"))
            object_count = len(detections) - human_count
            stat_str = f"HUMANS: {human_count} | OBJECTS: {object_count}"
            cv2.putText(frame, stat_str, (15, frame.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (16, 185, 129), 1, cv2.LINE_AA)

            self._draw_tactical_brackets(frame, frame.shape[1], frame.shape[0], (0, 242, 254))

            # Encode as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.035)

    def generate_thermal_frames(self):
        """Yields MJPEG stream of MLX90640 (Hardware or High-Res Simulation)."""
        frame_data = [0.0] * 768  # 32 columns x 24 rows
        sim_phase = 0.0

        while self.running:
            thermal_matrix = None

            if self.mlx_available:
                try:
                    self.mlx.getFrame(frame_data)
                    thermal_matrix = np.reshape(frame_data, (24, 32)).astype(np.float32)
                except Exception as e:
                    thermal_matrix = None

            if thermal_matrix is None:
                sim_phase += 0.06
                rows, cols = 24, 32
                thermal_matrix = np.random.normal(loc=26.5, scale=0.4, size=(rows, cols)).astype(np.float32)

                hot_cx = 16.0 + 8.0 * math.sin(sim_phase * 0.5)
                hot_cy = 12.0 + 5.0 * math.cos(sim_phase * 0.4)
                peak_temp = 48.5 + 4.0 * math.sin(sim_phase * 0.8)

                for y in range(rows):
                    for x in range(cols):
                        dist = math.sqrt((x - hot_cx)**2 + (y - hot_cy)**2)
                        if dist < 8.0:
                            thermal_matrix[y, x] += max(0.0, (peak_temp - 26.5) * math.exp(-0.35 * dist**2))

            min_temp = float(thermal_matrix.min())
            max_temp = float(thermal_matrix.max())
            avg_temp = float(thermal_matrix.mean())

            max_pos = np.unravel_index(np.argmax(thermal_matrix), thermal_matrix.shape)
            hot_y_grid, hot_x_grid = int(max_pos[0]), int(max_pos[1])

            h_pos = "CENTRE"
            if hot_x_grid < 10:
                h_pos = "LEFT"
            elif hot_x_grid > 21:
                h_pos = "RIGHT"
            v_pos = "MID"
            if hot_y_grid < 8:
                v_pos = "TOP"
            elif hot_y_grid > 15:
                v_pos = "BTM"
            hotspot_str = f"{v_pos}-{h_pos}"

            with self.lock:
                self.thermal_stats = {
                    "max_temp": round(max_temp, 1),
                    "min_temp": round(min_temp, 1),
                    "avg_temp": round(avg_temp, 1),
                    "hotspot": hotspot_str
                }

            norm_range = max(1.0, max_temp - min_temp)
            norm_img = ((thermal_matrix - min_temp) / norm_range * 255.0).clip(0, 255).astype(np.uint8)

            enlarged = cv2.resize(norm_img, (640, 480), interpolation=cv2.INTER_CUBIC)
            cmap = cv2.COLORMAP_INFERNO if self.colormap_mode == "INFERNO" else cv2.COLORMAP_JET
            color_thermal = cv2.applyColorMap(enlarged, cmap)

            screen_hot_x = int((hot_x_grid + 0.5) * (640.0 / 32.0))
            screen_hot_y = int((hot_y_grid + 0.5) * (480.0 / 24.0))

            reticle_color = (0, 255, 255)
            cv2.circle(color_thermal, (screen_hot_x, screen_hot_y), 24, reticle_color, 2)
            cv2.line(color_thermal, (screen_hot_x - 32, screen_hot_y), (screen_hot_x + 32, screen_hot_y), reticle_color, 1)
            cv2.line(color_thermal, (screen_hot_x, screen_hot_y - 32), (screen_hot_x, screen_hot_y + 32), reticle_color, 1)

            cv2.putText(color_thermal, f"HOT: {max_temp:.1f}C", (screen_hot_x + 12, screen_hot_y - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

            cv2.rectangle(color_thermal, (10, 10), (220, 95), (10, 14, 20), -1)
            cv2.rectangle(color_thermal, (10, 10), (220, 95), (60, 70, 85), 1)

            cv2.putText(color_thermal, f"MAX: {max_temp:.1f} C", (20, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 100, 255), 2)
            cv2.putText(color_thermal, f"AVG: {avg_temp:.1f} C", (20, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
            cv2.putText(color_thermal, f"MIN: {min_temp:.1f} C", (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 180, 50), 1)

            bar_x = 615
            for y_bar in range(60, 420):
                ratio = 1.0 - ((y_bar - 60) / 360.0)
                val_bar = int(ratio * 255)
                c = cv2.applyColorMap(np.array([[val_bar]], dtype=np.uint8), cmap)[0][0]
                color_thermal[y_bar, bar_x:bar_x + 12] = c
            cv2.rectangle(color_thermal, (bar_x, 60), (bar_x + 12, 420), (255, 255, 255), 1)

            cv2.putText(color_thermal, f"{int(max_temp)}C", (bar_x - 38, 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
            cv2.putText(color_thermal, f"{int(min_temp)}C", (bar_x - 38, 415), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

            self._draw_tactical_brackets(color_thermal, 640, 480, (0, 165, 255))

            ret, buffer = cv2.imencode('.jpg', color_thermal, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.06)