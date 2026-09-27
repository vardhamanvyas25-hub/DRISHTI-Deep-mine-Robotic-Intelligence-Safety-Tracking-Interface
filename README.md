# DRISHTI: Deep-mine Robotic Intelligence Safety Tracking Interface

**SIH 2026 Problem Statement ID:** 26039  
**Problem Statement Title:** AI-Powered Underground Mine Safety, Monitoring and Rescue System  
**Theme:** Smart Automation  
**Category:** Hardware
**Team Name:** Bare Metal
**Institution:** Sardar Patel Institute of Technology
**Branch:** EXTC

---

## 📌 Overview
DRISHTI is an AI-powered, fail-safe underground mine safety and rescue rover[cite: 1]. It enters hazardous underground coal mines ahead of human rescue teams to inspect toxic gases, extreme heat, and structural instability in real time[cite: 1]. Operating completely offline without cloud dependency[cite: 1], the system utilizes a two-layer control architecture combined with a tether-assisted backup connection to maintain reliability in subterranean environments[cite: 1].

---

## 👥 Team Members
* Vardhaman Vyas
* Madhan Bandi
* Harsh Chavan
* Amogh Sangodkar
* Namami Bansal
* Yukti Agrawal

---

## 🛠️ System Architecture

### Hardware Components
* **Safety Controller:** ESP32 / STM32 for low-level motor control, alarms, watchdog timer, and emergency fail-safe stops[cite: 1].
* **Onboard Computer:** Raspberry Pi for video streaming, thermal processing, and hosting the local web dashboard[cite: 1].
* **Gas Sensors:** MQ-2, MQ-4, and MQ-7 detecting Methane ($\text{CH}_4$), Carbon Monoxide ($\text{CO}$), Carbon Dioxide ($\text{CO}_2$), Oxygen ($\text{O}_2$), and Hydrogen Sulphide ($\text{H}_2\text{S}$)[cite: 1].
* **Environmental Sensors:** BME280 / SHT31 for ambient temperature and humidity tracking[cite: 1].
* **Thermal Camera:** MLX90640 thermal array for human heat signature, fire, and thermal zone detection[cite: 1].
* **Vision & Motion Sensors:** Pi Camera / USB UVC camera with IR night vision illumination, IMU for tilt/vibration/stability, VL53L1X / VL53L0X TOF sensors, wheel encoders, and optional 2D LiDAR[cite: 1].
* **Drivetrain & Power:** 4-wheel differential drive powered by geared DC motors and TB6612FNG drivers, backed by a protected 12V battery pack, BMS, and 5V/3.3V buck regulators[cite: 1].

### Communication & Software
* **Connectivity:** Wi-Fi for local data exchange, tether/Ethernet cable backup for subterranean reliability, and LoRa for emergency telemetry[cite: 1].
* **Dashboard:** Offline-first web dashboard providing real-time RGB/thermal feeds, live sensor telemetry, risk status, and manual rover overrides[cite: 1].
* **Fail-Safe Logic:** Rule-based decision pipeline evaluating conditions into **SAFE**, **WARNING**, or **DANGER** states[cite: 1]. Auto-stops motors and triggers alarms if communication heartbeats drop[cite: 1].

---

## 📂 Repository Structure
```text
├── arduino/
│   └── esp32_safety_controller/   # ESP32 firmware, motor control, safety state machine, watchdog
├── raspberry-pi/
│   ├── dashboard/                 # Offline web dashboard backend & frontend interface
│   ├── thermal_vision/            # MLX90640 thermal array and camera stream processing
│   └── telemetry/                # Sensor data fusion, logging, and risk scoring logic
├── vscode/
│   └── scripts/                   # Workspace configurations, utility scripts, & simulation models
└── README.md                      # Project documentation
