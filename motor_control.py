import sys
import json
import time
import threading
import urllib.request
import urllib.error

# Wrap RPi.GPIO import inside try...except so Windows/PC runs smoothly
try:
    import RPi.GPIO as GPIO
    HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError, ModuleNotFoundError):
    HARDWARE_AVAILABLE = False

# Left Driver Pins (BTS7960 #1 on Raspberry Pi)
L_EN = 17
RPWM_L = 12
LPWM_L = 13

# Right Driver Pins (BTS7960 #2 on Raspberry Pi)
R_EN = 27
RPWM_R = 18
LPWM_R = 19

class MotorController:
    def __init__(self, remote_rover_url="http://192.168.50.2:5000"):
        self.remote_url = remote_rover_url
        self.left_speed = 0.0
        self.right_speed = 0.0
        self.current_x = 0.0
        self.current_y = 0.0
        self.is_stopped = True
        self.is_estop = False
        self.running = True

        # Async Dispatcher Queue for Remote Rover (prevents HTTP latency from blocking Flask/UI)
        self.cmd_lock = threading.Lock()
        self.pending_cmd = None
        self.has_new_cmd = threading.Event()
        self.last_dispatched_vector = None
        self.remote_connected = True

        self.dispatcher_thread = threading.Thread(target=self._remote_dispatcher_loop, daemon=True)
        self.dispatcher_thread.start()

        # Hardware GPIO init if running directly on Raspberry Pi
        if HARDWARE_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)

                pins = [L_EN, RPWM_L, LPWM_L, R_EN, RPWM_R, LPWM_R]
                for pin in pins:
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, GPIO.LOW)

                GPIO.output(L_EN, GPIO.HIGH)
                GPIO.output(R_EN, GPIO.HIGH)

                self.pwms = {
                    'RPWM_L': GPIO.PWM(RPWM_L, 1000),
                    'LPWM_L': GPIO.PWM(LPWM_L, 1000),
                    'RPWM_R': GPIO.PWM(RPWM_R, 1000),
                    'LPWM_R': GPIO.PWM(LPWM_R, 1000)
                }

                for pwm in self.pwms.values():
                    pwm.start(0)
                print("[MOTORS] Local BTS7960 hardware PWM drivers initialized.")
            except Exception as e:
                print(f"[MOTORS] Local GPIO init error: {e}")
                self.pwms = {}
        else:
            self.pwms = {}
            print(f"[MOTORS] Remote drive mode active: Forwarding motor commands to {self.remote_url}/control")

    def _remote_dispatcher_loop(self):
        """Asynchronously dispatches drive and stop commands to the rover at http://192.168.50.2:5000."""
        while self.running:
            # Wait for a new command event with short timeout
            self.has_new_cmd.wait(timeout=0.1)
            self.has_new_cmd.clear()

            with self.cmd_lock:
                cmd = self.pending_cmd
                self.pending_cmd = None

            if cmd is None:
                continue

            try:
                cmd_type = cmd[0]
                if cmd_type == 'stop':
                    # Send STOP command
                    req = urllib.request.Request(
                        f"{self.remote_url}/stop",
                        data=b'{}',
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=0.8) as res:
                        pass

                    # Also send x:0, y:0 for safety redundancy
                    req_zero = urllib.request.Request(
                        f"{self.remote_url}/control",
                        data=json.dumps({"x": 0, "y": 0}).encode('utf-8'),
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    with urllib.request.urlopen(req_zero, timeout=0.8) as res:
                        pass

                    self.last_dispatched_vector = (0, 0)
                    self.remote_connected = True

                elif cmd_type == 'control':
                    x = cmd[1]
                    y = cmd[2]

                    # Skip duplicate identical vectors to minimize unnecessary network traffic
                    if self.last_dispatched_vector == (x, y) and (x != 0 or y != 0):
                        continue

                    req = urllib.request.Request(
                        f"{self.remote_url}/control",
                        data=json.dumps({"x": x, "y": y}).encode('utf-8'),
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=0.8) as res:
                        pass

                    self.last_dispatched_vector = (x, y)
                    self.remote_connected = True

            except Exception as e:
                self.remote_connected = False

    def set_motors(self, left_speed, right_speed):
        if self.is_estop:
            left_speed = 0.0
            right_speed = 0.0

        left_speed = max(-100.0, min(100.0, float(left_speed)))
        right_speed = max(-100.0, min(100.0, float(right_speed)))

        self.left_speed = round(left_speed, 1)
        self.right_speed = round(right_speed, 1)
        self.is_stopped = (abs(self.left_speed) < 1.0 and abs(self.right_speed) < 1.0)

        # Apply locally if on Raspberry Pi hardware
        if HARDWARE_AVAILABLE and self.pwms:
            try:
                if left_speed >= 0:
                    self.pwms['RPWM_L'].ChangeDutyCycle(left_speed)
                    self.pwms['LPWM_L'].ChangeDutyCycle(0)
                else:
                    self.pwms['RPWM_L'].ChangeDutyCycle(0)
                    self.pwms['LPWM_L'].ChangeDutyCycle(abs(left_speed))

                if right_speed >= 0:
                    self.pwms['RPWM_R'].ChangeDutyCycle(right_speed)
                    self.pwms['LPWM_R'].ChangeDutyCycle(0)
                else:
                    self.pwms['RPWM_R'].ChangeDutyCycle(0)
                    self.pwms['LPWM_R'].ChangeDutyCycle(abs(right_speed))
            except Exception:
                pass

    def drive(self, x, y):
        """Translates joystick vector (X: -100 to 100, Y: -100 to 100) and dispatches to rover."""
        self.is_estop = False
        x = max(-100.0, min(100.0, float(x)))
        y = max(-100.0, min(100.0, float(y)))
        self.current_x = round(x, 1)
        self.current_y = round(y, 1)

        left = y + x
        right = y - x
        self.set_motors(left, right)

        # Queue remote dispatch to 192.168.50.2/control
        with self.cmd_lock:
            self.pending_cmd = ('control', self.current_x, self.current_y)
            self.has_new_cmd.set()

    def command(self, cmd_name, speed=75):
        """Executes named directional commands (FORWARD, BACKWARD, LEFT, RIGHT, STOP, ESTOP)."""
        cmd = str(cmd_name).upper().strip()
        speed = float(speed)

        if cmd in ("ESTOP", "E_STOP", "EMERGENCY_STOP"):
            self.is_estop = True
            self.stop()
            return

        self.is_estop = False
        if cmd in ("FORWARD", "FWD", "UP"):
            self.drive(0, speed)
        elif cmd in ("BACKWARD", "REV", "DOWN"):
            self.drive(0, -speed)
        elif cmd in ("LEFT", "TURN_LEFT"):
            self.drive(-speed * 0.8, 0)
        elif cmd in ("RIGHT", "TURN_RIGHT"):
            self.drive(speed * 0.8, 0)
        elif cmd in ("STOP", "BRAKE"):
            self.stop()

    def stop(self):
        """Stops all motor movement and dispatches STOP to rover."""
        self.current_x = 0.0
        self.current_y = 0.0
        self.set_motors(0, 0)

        with self.cmd_lock:
            self.pending_cmd = ('stop',)
            self.has_new_cmd.set()

    def get_status(self):
        return {
            "left_speed": self.left_speed,
            "right_speed": self.right_speed,
            "x": self.current_x,
            "y": self.current_y,
            "is_stopped": self.is_stopped,
            "is_estop": self.is_estop,
            "remote_url": self.remote_url,
            "remote_connected": self.remote_connected,
            "hardware_active": HARDWARE_AVAILABLE
        }

    def cleanup(self):
        self.running = False
        self.stop()
        if HARDWARE_AVAILABLE and self.pwms:
            try:
                for pwm in self.pwms.values():
                    pwm.stop()
                GPIO.cleanup()
            except Exception:
                pass