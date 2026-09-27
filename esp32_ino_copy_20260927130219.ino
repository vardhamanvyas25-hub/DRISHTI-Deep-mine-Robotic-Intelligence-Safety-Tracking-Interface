#include <Arduino.h>
#include <Wire.h>
#include <DHT.h>
#include <Adafruit_BMP280.h>

// Safe GPIO Mapping for ESP32-S3
#define RX_PIN 18         // Connect to Raspberry Pi Pin 8 (TXD)
#define TX_PIN 17         // Connect to Raspberry Pi Pin 10 (RXD)

#define MQ4_PIN 4         // Methane Analog Input (GPIO 4)
#define MQ7_PIN 5         // CO Analog Input (GPIO 5)
#define BATTERY_PIN 6     // Battery Voltage Divider (GPIO 6)
#define DHT_PIN 7         // DHT11 Data Pin (GPIO 7)

#define DHTTYPE DHT11

DHT dht(DHT_PIN, DHTTYPE);
Adafruit_BMP280 bmp; // Uses Default I2C (SDA: GPIO 8, SCL: GPIO 9 or default wire pins)

String getTelemetryJSON();

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Set Hardware Serial2 to Raspberry Pi Bridge
  Serial2.begin(115200, SERIAL_8N1, RX_PIN, TX_PIN);

  // CRITICAL: Set ADC attenuation to 11dB (allows 0V - 3.1V input range)
  analogSetAttenuation(ADC_11db);

  // Initialize Sensors
  dht.begin();
  if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
    Serial.println("[WARNING] BMP280 sensor not found on I2C!");
  }

  pinMode(MQ4_PIN, INPUT);
  pinMode(MQ7_PIN, INPUT);
  pinMode(BATTERY_PIN, INPUT);

  Serial.println("[ESP32-S3] Telemetry Engine Online.");
}

void loop() {
  String jsonTelemetry = getTelemetryJSON();

  // Transmit telemetry to both Serial Monitor and Raspberry Pi
  Serial.println(jsonTelemetry);
  Serial2.println(jsonTelemetry);

  delay(200); // 5 Hz update interval
}

String getTelemetryJSON() {
  // 1. Read Analog Sensors (0 to 4095 @ 3.3V full scale)
  int mq4Raw = analogRead(MQ4_PIN);
  int mq7Raw = analogRead(MQ7_PIN);
  int battRaw = analogRead(BATTERY_PIN);

  // Map analog readings to PPM and Voltage
  float methanePpm = map(mq4Raw, 0, 4095, 0, 1000);
  float coPpm = map(mq7Raw, 0, 4095, 0, 500);

  // Calculate battery voltage (assuming 1:4 voltage divider for 12V Li-Ion pack)
  float rawVoltage = (battRaw / 4095.0) * 3.3;
  float actualBatteryVoltage = rawVoltage * 4.0; 
  int batteryPct = map(battRaw, 2500, 3900, 0, 100);
  batteryPct = constrain(batteryPct, 0, 100);

  // 2. Read Digital Sensors (DHT11 & BMP280)
  float tempC = dht.readTemperature();
  float humidity = dht.readHumidity();
  float pressure = bmp.readPressure() / 100.0F; // Convert Pa to hPa

  // Handle sensor read errors with fallbacks
  if (isnan(tempC)) tempC = 25.0;
  if (isnan(humidity)) humidity = 50.0;
  if (isnan(pressure) || pressure == 0) pressure = 1013.25;

  int noiseDb = 40 + (analogRead(4) % 15); // Simulated ambient acoustics baseline

  // Construct JSON
  String json = "{";
  json += "\"methane\":" + String(methanePpm, 1) + ",";
  json += "\"co\":" + String(coPpm, 1) + ",";
  json += "\"temp\":" + String(tempC, 1) + ",";
  json += "\"humidity\":" + String(humidity, 1) + ",";
  json += "\"pressure\":" + String(pressure, 2) + ",";
  json += "\"voltage\":" + String(actualBatteryVoltage, 1) + ",";
  json += "\"battery\":" + String(batteryPct) + ",";
  json += "\"noise\":" + String(noiseDb);
  json += "}";

  return json;
}