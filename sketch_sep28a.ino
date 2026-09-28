#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <driver/i2s.h>

// --- PIN DEFINITIONS (Based on Wiring Specification) ---
#define DHTPIN        4
#define DHTTYPE       DHT11

#define BMP_SDA       8
#define BMP_SCL       9

#define MQ4_ADC_PIN   1   // LV1 from Level Converter (Methane)
#define MQ7_ADC_PIN   2   // LV2 from Level Converter (CO)
#define BATT_ADC_PIN  3   // Scaled Battery Voltage

// I2S Microphone (INMP441)
#define I2S_WS        13
#define I2S_SD        14
#define I2S_SCK       12
#define I2S_PORT      I2S_NUM_0

// Hardware Serial 2 for Pi 4B Communication
#define UART_TX_PIN   17  // ESP32 TX2 -> Pi RXD (GPIO 15)
#define UART_RX_PIN   18  // ESP32 RX2 -> Pi TXD (GPIO 14)

// --- OBJECT INSTANTIATIONS ---
DHT dht(DHTPIN, DHTTYPE);
Adafruit_BMP280 bmp; // Uses I2C Wire

// --- I2S MIC SETUP ---
void setupI2S() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 512,
    .use_apll = false
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);
}

int readMicAudioPeak() {
  int32_t sample_buffer[256];
  size_t bytes_read = 0;
  i2s_read(I2S_PORT, &sample_buffer, sizeof(sample_buffer), &bytes_read, portMAX_DELAY);
  
  int max_val = 0;
  int samples = bytes_read / sizeof(int32_t);
  for (int i = 0; i < samples; i++) {
    int abs_val = abs(sample_buffer[i] >> 16);
    if (abs_val > max_val) {
      max_val = abs_val;
    }
  }
  return map(constrain(max_val, 0, 10000), 0, 10000, 0, 100);
}

void setup() {
  // Primary Serial Debug
  Serial.begin(115200);

  // Serial2 Hardware Connection to Pi 4B
  Serial2.begin(115200, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);

  // ADC Calibration & Resolution
  analogReadResolution(12);

  // Sensor Initialization
  dht.begin();
  Wire.begin(BMP_SDA, BMP_SCL);
  if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
    Serial.println("BMP280 Sensor not found!");
  }

  setupI2S();
  Serial.println("ESP32-S3 Telemetry Node Ready.");
}

void loop() {
  static unsigned long lastSendTime = 0;
  if (millis() - lastSendTime >= 200) { // 5 Hz update rate
    lastSendTime = millis();

    // 1. Read DHT11
    float humidity = dht.readHumidity();
    float temp_dht = dht.readTemperature();

    // 2. Read BMP280
    float pressure = bmp.readPressure() / 100.0F; // Convert Pa to hPa
    float temp_bmp = bmp.readTemperature();

    // 3. Read Analog Gas Sensors
    int raw_mq4 = analogRead(MQ4_ADC_PIN);
    int raw_mq7 = analogRead(MQ7_ADC_PIN);

    // 4. Read Battery Voltage (0-25V Sensor with 5:1 Divider)
    int raw_batt = analogRead(BATT_ADC_PIN);
    float battery_v = (raw_batt / 4095.0) * 3.3 * 5.0;

    // 5. Read Audio Activeness Level
    int audio_level = readMicAudioPeak();

    // 6. Build JSON Document
    StaticJsonDocument<256> doc;
    doc["temp_dht"] = isnan(temp_dht) ? 0.0 : temp_dht;
    doc["hum_dht"]  = isnan(humidity) ? 0.0 : humidity;
    doc["press_bmp"]= isnan(pressure) ? 0.0 : pressure;
    doc["mq4"]      = raw_mq4;
    doc["mq7"]      = raw_mq7;
    doc["battery_v"]= battery_v;
    doc["audio"]    = audio_level;

    // Serialize and Send over Serial2
    String output;
    serializeJson(doc, output);
    Serial2.println(output);
    Serial.println(output); // Debug output
  }
}