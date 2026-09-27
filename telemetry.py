import time


DEFAULT = {
    "temp_c": 27.6,
    "humidity_pct": 62.0,
    "pressure_hpa": 1012.8,
    "mq4_raw": 650,
    "mq7_raw": 420,
    "distance_cm": 120,
    "tilt_deg": 2.0,
    "battery_v": 12.6,
    "battery_a": 1.2,
    "water_detected": False,
    "rover_state": "READY",
    "link_ok": True,
    "received_at": 0.0
}


SCENARIOS = {
    "SAFE": {
        **DEFAULT,
        "temp_c": 27.6,
        "mq4_raw": 650,
        "mq7_raw": 420,
        "distance_cm": 120,
        "tilt_deg": 2.0,
        "battery_v": 12.6,
        "water_detected": False,
        "rover_state": "READY",
        "link_ok": True
    },

    "GAS_LEAK": {
        **DEFAULT,
        "temp_c": 34.0,
        "mq4_raw": 1950,
        "mq7_raw": 1690,
        "distance_cm": 75,
        "tilt_deg": 3.0,
        "battery_v": 12.3,
        "rover_state": "HAZARD_DETECTED",
        "link_ok": True
    },

    "OBSTACLE": {
        **DEFAULT,
        "distance_cm": 14,
        "tilt_deg": 5.0,
        "battery_v": 12.2,
        "rover_state": "OBSTACLE_CLOSE",
        "link_ok": True
    },

    "TILT_DANGER": {
        **DEFAULT,
        "distance_cm": 85,
        "tilt_deg": 31.0,
        "battery_v": 12.1,
        "rover_state": "TILT_DANGER",
        "link_ok": True
    },

    "LOW_BATTERY": {
        **DEFAULT,
        "distance_cm": 90,
        "tilt_deg": 3.0,
        "battery_v": 10.65,
        "rover_state": "LOW_BATTERY",
        "link_ok": True
    },

    "WATER_LEAK": {
        **DEFAULT,
        "distance_cm": 85,
        "battery_v": 12.2,
        "water_detected": True,
        "rover_state": "WATER_ALERT",
        "link_ok": True
    },

    "LINK_LOST": {
        **DEFAULT,
        "temp_c": None,
        "humidity_pct": None,
        "pressure_hpa": None,
        "mq4_raw": None,
        "mq7_raw": None,
        "distance_cm": None,
        "tilt_deg": None,
        "battery_v": None,
        "battery_a": None,
        "water_detected": False,
        "rover_state": "LINK_LOST",
        "link_ok": False
    }
}


class RoverSimulator:
    def __init__(self):
        self.scenario = "SAFE"
        self.drive_state = "STOPPED"
        self.light_on = False
        self.events = []

        self.add_event(
            "SYSTEM_READY",
            "Laptop-only simulation is running"
        )

    def add_event(self, event, details):
        self.events.insert(0, {
            "time": time.strftime("%H:%M:%S"),
            "event": event,
            "details": details
        })

        self.events = self.events[:30]

    def set_scenario(self, scenario):
        if scenario not in SCENARIOS:
            return False

        self.scenario = scenario

        if scenario == "LINK_LOST":
            self.drive_state = "FAILSAFE_STOP"

        self.add_event(
            "SCENARIO",
            f"Changed to {scenario.replace('_', ' ')}"
        )

        return True

    def command(self, command, speed=150):
        allowed = {
            "FWD",
            "REV",
            "LEFT",
            "RIGHT",
            "STOP",
            "ESTOP",
            "LIGHT_ON",
            "LIGHT_OFF"
        }

        if command not in allowed:
            return False, "Invalid command"

        if command == "ESTOP":
            self.drive_state = "EMERGENCY_STOP"

            self.add_event(
                "EMERGENCY_STOP",
                "Manual emergency stop applied"
            )

            return True, "Emergency stop applied"

        if self.scenario == "LINK_LOST":
            self.drive_state = "FAILSAFE_STOP"

            self.add_event(
                "COMMAND_BLOCKED",
                "Link lost: failsafe stop is active"
            )

            return False, "Blocked: link-loss failsafe active"

        if command == "STOP":
            self.drive_state = "STOPPED"

        elif command == "LIGHT_ON":
            self.light_on = True

        elif command == "LIGHT_OFF":
            self.light_on = False

        else:
            self.drive_state = f"{command} @ {speed}"

        self.add_event(
            "COMMAND",
            f"{command} speed={speed}"
        )

        return True, "Command accepted"

    def telemetry(self):
        data = SCENARIOS[self.scenario].copy()

        data["received_at"] = time.time()
        data["drive_state"] = self.drive_state
        data["light_on"] = self.light_on

        data["sensor_health"] = {
            "gas": "SIMULATED",
            "environment": "SIMULATED",
            "distance": "SIMULATED",
            "imu": "SIMULATED",
            "battery": "SIMULATED"
        }

        return data