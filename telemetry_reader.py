import threading
import time
import json
import math
import random

try:
    import serial
    import serial.tools.list_ports as list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    list_ports = None

def get_available_ports():
    """Returns a list of available serial ports with details."""
    if not SERIAL_AVAILABLE or list_ports is None:
        return []
    ports = []
    for p in list_ports.comports():
        ports.append({
            "device": p.device,
            "description": p.description or p.device,
            "hwid": p.hwid or ""
        })
    return ports

def auto_detect_esp32_port():
    """Auto-detects an ESP32 or USB-Serial device port."""
    if not SERIAL_AVAILABLE or list_ports is None:
        return "COM3"
    com_ports = list_ports.comports()
    # Preferred matches for ESP32 / Arduino / USB serial chips
    keywords = ["ch34", "cp210", "ftdi", "usb-serial", "uart", "esp32", "arduino"]
    for p in com_ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        for kw in keywords:
            if kw in desc or kw in hwid:
                return p.device
    # If COM3 exists, default to COM3
    for p in com_ports:
        if p.device.upper() == "COM3":
            return "COM3"
    # Otherwise first available or COM3
    if com_ports:
        return com_ports[0].device
    return "COM3"

class TelemetryReader(threading.Thread):
    def __init__(self, port="AUTO", baudrate=115200):
        super().__init__()
        self.requested_port = port
        self.port = auto_detect_esp32_port() if port == "AUTO" else port
        self.baudrate = baudrate
        self.daemon = True
        self.running = True
        self.lock = threading.Lock()

        # Telemetry State
        self.data = {
            "mq4_raw": 520,
            "mq7_raw": 340,
            "temp_c": 27.4,
            "humidity_pct": 58.2,
            "pressure_hpa": 1013.1,
            "battery_v": 12.18,
            "battery_pct": 85,
            "rover_state": "READY",
            "link_ok": True,
            "connected": False,
            "is_simulated": True,
            "port_status": "INITIALIZING",
            "status_message": "Scanning for ESP32...",
            "port": self.port,
            "baudrate": self.baudrate,
            "packets_received": 0,
            "last_packet_time": 0.0,
            "gas_hazard_level": "SAFE",
            
            # Compatibility aliases
            "temp_dht": 27.4,
            "hum_dht": 58.2,
            "press_bmp": 1013.1,
            "mq4": 520,
            "mq7": 340,
            "battery_voltage": 12.18,
            "audio": 42
        }

        # Simulation generator parameters
        self._sim_t = 0.0

    def set_port(self, new_port):
        """Allows switching port dynamically."""
        with self.lock:
            self.requested_port = new_port
            self.port = auto_detect_esp32_port() if new_port == "AUTO" else new_port
            self.data["port"] = self.port
            self.data["port_status"] = "SWITCHING"
            self.data["status_message"] = f"Switching to port {self.port}..."

    def _update_simulation_step(self):
        """Generates realistic sensor oscillations when real ESP32 is offline or port is busy."""
        self._sim_t += 0.2
        # Slight sinusoidal oscillation around realistic baselines
        mq4_sim = int(480 + 45 * math.sin(self._sim_t * 0.4) + random.uniform(-10, 10))
        mq7_sim = int(320 + 35 * math.sin(self._sim_t * 0.3) + random.uniform(-8, 8))
        temp_sim = round(27.0 + 1.2 * math.sin(self._sim_t * 0.1) + random.uniform(-0.1, 0.1), 1)
        hum_sim = round(58.0 + 3.0 * math.sin(self._sim_t * 0.15) + random.uniform(-0.3, 0.3), 1)
        press_sim = round(1013.25 + 0.8 * math.sin(self._sim_t * 0.05), 1)
        batt_sim = round(12.25 - (self._sim_t * 0.0005) % 0.5, 2)
        batt_pct_sim = max(0, min(100, int((batt_sim - 10.5) / (12.6 - 10.5) * 100)))

        with self.lock:
            self.data.update({
                "mq4_raw": mq4_sim,
                "mq7_raw": mq7_sim,
                "temp_c": temp_sim,
                "humidity_pct": hum_sim,
                "pressure_hpa": press_sim,
                "battery_v": batt_sim,
                "battery_pct": batt_pct_sim,
                "rover_state": "READY (SIM)",
                "link_ok": True,
                "connected": False,
                "is_simulated": True,
                "mq4": mq4_sim,
                "mq7": mq7_sim,
                "temp_dht": temp_sim,
                "hum_dht": hum_sim,
                "press_bmp": press_sim,
                "battery_voltage": batt_sim,
                "gas_hazard_level": "SAFE"
            })

    def run(self):
        while self.running:
            if not SERIAL_AVAILABLE:
                self.data["port_status"] = "NO_PYSERIAL"
                self.data["status_message"] = "pyserial not available, running simulation mode"
                self._update_simulation_step()
                time.sleep(0.3)
                continue

            current_target = self.port
            ser = None
            try:
                ser = serial.Serial(current_target, self.baudrate, timeout=1.0)
                time.sleep(0.5)  # Allow DTR/RTS to settle
                
                with self.lock:
                    self.data["connected"] = True
                    self.data["is_simulated"] = False
                    self.data["port_status"] = "CONNECTED"
                    self.data["status_message"] = f"Connected to {current_target} at {self.baudrate} baud"
                    self.data["port"] = current_target

                print(f"[TELEMETRY] Successfully opened {current_target} at {self.baudrate} baud.")

                while self.running:
                    # Check if port changed externally
                    if self.requested_port != "AUTO" and self.port != current_target:
                        break

                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line:
                        # Extract JSON object substring
                        start_idx = line.find('{')
                        end_idx = line.rfind('}')
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            json_str = line[start_idx:end_idx + 1]
                            try:
                                payload = json.loads(json_str)
                                self._process_esp32_payload(payload)
                            except json.JSONDecodeError:
                                pass
                    time.sleep(0.02)

            except (serial.SerialException, PermissionError, OSError) as e:
                err_str = str(e)
                with self.lock:
                    self.data["connected"] = False
                    self.data["is_simulated"] = True
                    if "PermissionError" in err_str or "Access is denied" in err_str:
                        self.data["port_status"] = "BUSY_LOCKED"
                        self.data["status_message"] = f"Port {current_target} is in use (e.g. Arduino IDE Serial Monitor open). Close it to connect."
                    elif "could not open port" in err_str or "FileNotFoundError" in err_str:
                        self.data["port_status"] = "NOT_FOUND"
                        self.data["status_message"] = f"Port {current_target} not found. Plug in ESP32."
                    else:
                        self.data["port_status"] = "ERROR"
                        self.data["status_message"] = f"Serial error: {err_str[:60]}"

                # Update simulation while disconnected/busy
                for _ in range(5):
                    if not self.running:
                        break
                    self._update_simulation_step()
                    time.sleep(0.3)

                # Re-check auto port if set to AUTO
                if self.requested_port == "AUTO":
                    new_detected = auto_detect_esp32_port()
                    if new_detected != self.port:
                        self.port = new_detected
                        self.data["port"] = self.port

            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

    def _process_esp32_payload(self, payload):
        """Processes and normalizes raw JSON emitted by esp32_ino_copy_20260927130219.ino."""
        with self.lock:
            # Raw gas sensors (ADC 0-4095)
            mq4_raw = int(payload.get("mq4_raw", payload.get("mq4", self.data["mq4_raw"])))
            mq7_raw = int(payload.get("mq7_raw", payload.get("mq7", self.data["mq7_raw"])))

            # Environmental readings
            temp_c = float(payload.get("temp_c", payload.get("temp_dht", self.data["temp_c"])))
            hum_pct = float(payload.get("humidity_pct", payload.get("hum_dht", self.data["humidity_pct"])))
            press_hpa = float(payload.get("pressure_hpa", payload.get("press_bmp", self.data["pressure_hpa"])))

            # Battery voltage
            battery_v = float(payload.get("battery_v", payload.get("battery_voltage", self.data["battery_v"])))
            # Approximate percentage for 3S LiPo (10.5V empty, 12.6V full)
            if battery_v > 9.0:
                batt_pct = max(0, min(100, int((battery_v - 10.5) / (12.6 - 10.5) * 100)))
            else:
                batt_pct = max(0, min(100, int((battery_v / 4.2) * 100)))

            rover_state = str(payload.get("rover_state", "READY"))
            link_ok = bool(payload.get("link_ok", True))

            # Gas Hazard Rating
            gas_hazard = "SAFE"
            if mq4_raw > 1800 or mq7_raw > 1600:
                gas_hazard = "CRITICAL HAZARD"
            elif mq4_raw > 1100 or mq7_raw > 900:
                gas_hazard = "ELEVATED RISK"

            # Update state dictionary
            self.data.update({
                "mq4_raw": mq4_raw,
                "mq7_raw": mq7_raw,
                "temp_c": round(temp_c, 1),
                "humidity_pct": round(hum_pct, 1),
                "pressure_hpa": round(press_hpa, 1),
                "battery_v": round(battery_v, 2),
                "battery_pct": batt_pct,
                "rover_state": rover_state,
                "link_ok": link_ok,
                "connected": True,
                "is_simulated": False,
                "port_status": "CONNECTED",
                "status_message": f"Live Hardware Feed from {self.port}",
                "packets_received": self.data["packets_received"] + 1,
                "last_packet_time": time.time(),
                "gas_hazard_level": gas_hazard,
                
                # Aliases
                "mq4": mq4_raw,
                "mq7": mq7_raw,
                "temp_dht": round(temp_c, 1),
                "hum_dht": round(hum_pct, 1),
                "press_bmp": round(press_hpa, 1),
                "battery_voltage": round(battery_v, 2)
            })

    def get_telemetry(self):
        with self.lock:
            d = dict(self.data)
            # Add telemetry age
            if d["last_packet_time"] > 0:
                d["telemetry_age"] = round(time.time() - d["last_packet_time"], 1)
            else:
                d["telemetry_age"] = 0.0
            return d

    def stop(self):
        self.running = False