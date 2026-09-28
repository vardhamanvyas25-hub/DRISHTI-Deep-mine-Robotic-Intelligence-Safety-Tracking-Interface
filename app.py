import os
import sys
import time
import threading
from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit

# Ensure local imports find files in current directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from motor_control import MotorController
from telemetry_reader import TelemetryReader, get_available_ports
from camera_streamer import CameraStreamer

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'),
                      static_folder=os.path.join(BASE_DIR, 'static'))
app.config['SECRET_KEY'] = 'drishti_rover_command_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize System Modules
print("[SYSTEM] Starting DRISHTI Command & Control Engine...")
motor = MotorController()
telemetry = TelemetryReader()
telemetry.start()
cameras = CameraStreamer()

def calculate_hazard_assessment(t_data, detections, thermal_stats):
    """Computes real-time multi-sensor composite hazard rating (0-100)."""
    mq4 = t_data.get("mq4_raw", 0)
    mq7 = t_data.get("mq7_raw", 0)
    max_temp = thermal_stats.get("max_temp", 26.0)

    score = 8
    # Methane Risk
    if mq4 > 1800:
        score += 38
    elif mq4 > 1100:
        score += 20
    elif mq4 > 700:
        score += 8

    # Carbon Monoxide Risk
    if mq7 > 1500:
        score += 35
    elif mq7 > 900:
        score += 18
    elif mq7 > 500:
        score += 8

    # Thermal Hotspot Risk
    if max_temp > 50.0:
        score += 28
    elif max_temp > 40.0:
        score += 15
    elif max_temp > 33.0:
        score += 6

    # Target Detection Presence
    if any(d.get("class") == "person" for d in detections):
        score += 10
    if any(d.get("class") == "hazard" for d in detections):
        score += 15

    score = min(score, 100)

    if score >= 70:
        hazard_class = "CRITICAL HAZARD"
        hazard_color = "#ef4444"
    elif score >= 40:
        hazard_class = "ELEVATED RISK"
        hazard_color = "#f59e0b"
    else:
        hazard_class = "SAFE OPERATIONAL"
        hazard_color = "#10b981"

    return {
        "score": score,
        "class": hazard_class,
        "color": hazard_color
    }

def get_full_system_status():
    t_data = telemetry.get_telemetry()
    detections = cameras.latest_detections
    thermal = cameras.thermal_stats
    motors = motor.get_status()
    hazard = calculate_hazard_assessment(t_data, detections, thermal)

    return {
        "telemetry": t_data,
        "yolo_detections": detections,
        "thermal_stats": thermal,
        "motors": motors,
        "hazard": hazard,
        "timestamp": time.time()
    }

# Background Telemetry Pusher (150ms interval)
def telemetry_broadcast_loop():
    while True:
        try:
            status = get_full_system_status()
            # Emit full state payload
            socketio.emit('telemetry_data', status)
        except Exception as e:
            pass
        time.sleep(0.15)

# --- Web Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
@app.route('/api/rgb-feed')
def video_feed():
    return Response(cameras.generate_webcam_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/thermal_feed')
@app.route('/api/thermal-feed')
def thermal_feed():
    return Response(cameras.generate_thermal_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/telemetry')
@app.route('/api/telemetry')
def get_telemetry_endpoint():
    return jsonify(telemetry.get_telemetry())

@app.route('/api/status')
def get_status_endpoint():
    return jsonify(get_full_system_status())

@app.route('/control', methods=['POST'])
@app.route('/api/control', methods=['POST'])
def handle_control_post():
    data = request.get_json(silent=True) or {}
    if 'command' in data:
        motor.command(data['command'], speed=data.get('speed', 75))
    elif 'x' in data or 'y' in data:
        x = float(data.get('x', 0))
        y = float(data.get('y', 0))
        motor.drive(x, y)
    return jsonify({"status": "ok", "motor_state": motor.get_status()})

@app.route('/stop', methods=['POST'])
@app.route('/api/stop', methods=['POST'])
def handle_stop_post():
    motor.command("ESTOP")
    return jsonify({"status": "emergency_stop_applied", "motor_state": motor.get_status()})

@app.route('/api/ports', methods=['GET'])
def get_ports_endpoint():
    return jsonify({
        "available_ports": get_available_ports(),
        "active_port": telemetry.port,
        "port_status": telemetry.data.get("port_status", "UNKNOWN"),
        "status_message": telemetry.data.get("status_message", "")
    })

@app.route('/api/select-port', methods=['POST'])
def select_port_endpoint():
    data = request.get_json(silent=True) or {}
    new_port = data.get('port', 'AUTO')
    telemetry.set_port(new_port)
    return jsonify({
        "status": "success",
        "active_port": telemetry.port
    })

@app.route('/api/colormap', methods=['POST'])
def set_colormap_endpoint():
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'INFERNO')
    cameras.set_colormap(mode)
    return jsonify({"status": "success", "mode": cameras.colormap_mode})

# --- WebSocket Events ---
@socketio.on('connect')
def handle_connect():
    emit('telemetry_data', get_full_system_status())

@socketio.on('drive_cmd')
def handle_drive_ws(data):
    x = float(data.get('x', 0))
    y = float(data.get('y', 0))
    motor.drive(x, y)

@socketio.on('command')
def handle_command_ws(data):
    cmd = data.get('cmd', 'STOP')
    spd = data.get('speed', 75)
    motor.command(cmd, spd)

@socketio.on('e_stop')
def handle_estop_ws():
    motor.command("ESTOP")

if __name__ == '__main__':
    # Start background telemetry pusher thread
    t = threading.Thread(target=telemetry_broadcast_loop)
    t.daemon = True
    t.start()

    print("[SYSTEM] Command Centre Web Interface initialized.")
    print("[SYSTEM] Access dashboard at: http://localhost:5000")
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    finally:
        motor.cleanup()
