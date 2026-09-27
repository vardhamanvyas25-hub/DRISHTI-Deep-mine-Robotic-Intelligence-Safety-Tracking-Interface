import os
import time
import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory, Response

os.environ["OPENCV_LOG_LEVEL"] = "FATAL"

app = Flask(__name__, static_folder="static")

# Video Stream Configuration
RASPBERRY_PI_IP = "127.0.0.1"
WEBCAM_STREAM_URL = f"http://{RASPBERRY_PI_IP}:8000/webcam.mjpg"
THERMAL_STREAM_URL = f"http://{RASPBERRY_PI_IP}:8000/thermal.mjpg"

latest_yolo_detections = []
pending_rover_command = None

latest_telemetry = {
    "methane": 0,
    "co": 0,
    "temp": 24.5,
    "humidity": 48,
    "pressure": 1013.2,
    "voltage": 12.1,
    "battery": 95,
    "noise": 38
}

# Initialize YOLOv8 Model
yolo_model = None
try:
    from ultralytics import YOLO
    yolo_model = YOLO("yolov8n.pt")
    print("[INFO] YOLOv8 Model loaded successfully!")
except Exception as e:
    print(f"[WARNING] Could not initialize Ultralytics YOLO: {e}")

# Frame Generator for Optical Stream + Target Detection
def generate_optical_stream():
    global latest_yolo_detections
    
    # Force OpenCV to use the FFMPEG backend for network streams
    cap = cv2.VideoCapture(WEBCAM_STREAM_URL, cv2.CAP_FFMPEG)

    while True:
        success, frame = cap.read()
        if success and frame is not None:
            if yolo_model is not None:
                try:
                    results = yolo_model(frame, conf=0.35, verbose=False)[0]
                    annotated_frame = results.plot()

                    detections = []
                    for box in results.boxes:
                        cls_id = int(box.cls[0])
                        label = yolo_model.names[cls_id]
                        conf = round(float(box.conf[0]), 2)
                        detections.append({"class": label, "confidence": conf})
                    
                    latest_yolo_detections = detections
                except Exception:
                    annotated_frame = frame
            else:
                annotated_frame = frame

            ret, buffer = cv2.imencode('.jpg', annotated_frame)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.03)
        else:
            # Re-attempt connection if stream drops
            cap.release()
            time.sleep(1.0)
            cap = cv2.VideoCapture(WEBCAM_STREAM_URL, cv2.CAP_FFMPEG)

# Frame Generator for Thermal Stream
def generate_thermal_stream():
    cap = cv2.VideoCapture(THERMAL_STREAM_URL)
    while True:
        success, frame = cap.read()
        if success and frame is not None:
            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(0.05)
                continue
        
        cap.release()
        time.sleep(0.5)
        cap = cv2.VideoCapture(THERMAL_STREAM_URL)

        # Tactical Thermal Standby Frame
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(blank, (15, 15), (625, 465), (30, 40, 60), 1)
        cv2.line(blank, (320, 200), (320, 280), (0, 165, 255), 1)
        cv2.line(blank, (280, 240), (360, 240), (0, 165, 255), 1)
        cv2.circle(blank, (320, 240), 30, (0, 165, 255), 1)
        
        cv2.putText(blank, "THERMAL CAMERA STANDBY", (190, 220),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 165, 255), 2, cv2.LINE_AA)
        cv2.putText(blank, "MLX90640 THERMAL SENSOR OFFLINE", (170, 275),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1, cv2.LINE_AA)

        ret, buffer = cv2.imencode('.jpg', blank)
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.5)

# API Routes
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/telemetry", methods=["POST"])
def receive_telemetry():
    global latest_telemetry
    data = request.get_json(silent=True)
    if data:
        latest_telemetry.update(data)
        return jsonify({"status": "success"}), 200
    return jsonify({"error": "invalid json"}), 400

@app.route("/api/control", methods=["POST"])
def send_control():
    global pending_rover_command
    data = request.get_json(silent=True)
    if data and "command" in data:
        pending_rover_command = data["command"]
        return jsonify({"status": "queued"}), 200
    return jsonify({"error": "invalid command"}), 400

@app.route("/api/get-command", methods=["GET"])
def get_command():
    global pending_rover_command
    cmd = pending_rover_command
    pending_rover_command = None
    return jsonify({"command": cmd})

@app.route("/api/status")
def status():
    methane = latest_telemetry.get("methane", 0)
    co = latest_telemetry.get("co", 0)
    
    score = 10
    if methane > 30: score += 40
    if co > 25: score += 35
    if any(d["class"] == "person" for d in latest_yolo_detections): score += 15
    score = min(score, 100)

    hazard_class = "CRITICAL HAZARD" if score >= 70 else ("ELEVATED RISK" if score >= 40 else "SAFE")

    return jsonify({
        "telemetry": latest_telemetry,
        "yolo_detections": latest_yolo_detections,
        "hazard": {"score": score, "class": hazard_class}
    })

@app.route("/api/rgb-feed")
def rgb_feed():
    return Response(generate_optical_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/api/thermal-feed")
def thermal_feed():
    return Response(generate_thermal_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)