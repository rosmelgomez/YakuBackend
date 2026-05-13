/*
  ============================================================
  SISTEMA DE RIEGO – ESP32-S3 + MQTT HiveMQ Cloud
  Broker : 85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud
  Puerto : 8883 (TLS)
  ============================================================
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

// ── WiFi ──────────────────────────────────────────────────────────
const char* ssid     = "HGB_2,4GHz";
const char* password = "@Hgb153427986@";

// ── HiveMQ Cloud ──────────────────────────────────────────────────
const char* mqtt_host     = "85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud";
const uint16_t mqtt_port  = 8883;
const char* mqtt_user     = "hivemq.webclient.1778630712813";
const char* mqtt_password = "pVA$d1KU,>R7gM30b@vo";
const char* mqtt_client_id = "ESP32_Yaku_001";

// ── Topics ────────────────────────────────────────────────────────
// Topics to match FastAPI backend defaults
const char* TOPIC_SENSORES  = "yaku/riego/datos";       // ESP32 publica aquí (datos de riego)
const char* TOPIC_VALVULA   = "yaku/riego/control_agua"; // ESP32 escucha aquí (comandos de válvula)
const char* TOPIC_STATUS    = "yaku/status";         // heartbeat

// ── Pines ─────────────────────────────────────────────────────────
#define PIN_SUELO     4
#define DHTPIN        15
#define DHTTYPE       DHT22
#define ONE_WIRE_BUS  16
#define PIN_VALVULA   17   // relay/válvula solenoide

// ── Calibración sensor de suelo ───────────────────────────────────
#define ADC_SECO    3200
#define ADC_MOJADO  1200

// ── Objetos sensores ──────────────────────────────────────────────
DHT dht(DHTPIN, DHTTYPE);
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);

// ── Variables compartidas ─────────────────────────────────────────
SemaphoreHandle_t xMutex;
int   adc_suelo     = 0;
float humedad_suelo = 0.0f;
float temp_suelo    = -127.0f;
float temp_amb      = NAN;
float hum_amb       = NAN;

// ── Clientes MQTT ─────────────────────────────────────────────────
WiFiClientSecure espClient;
PubSubClient     mqttClient(espClient);

// ══════════════════════════════════════════════════════════════════
// WIFI
// ══════════════════════════════════════════════════════════════════
void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.println("Conectando WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  uint8_t intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(1000); Serial.print("."); intentos++;
  }
  if (WiFi.status() == WL_CONNECTED)
    Serial.println("\n✅ WiFi: " + WiFi.localIP().toString());
  else
    Serial.println("\n❌ WiFi sin conexión");
}

// ══════════════════════════════════════════════════════════════════
// MQTT – CALLBACK (mensajes entrantes)
// ══════════════════════════════════════════════════════════════════
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  Serial.printf("📥 [%s] %s\n", topic, msg.c_str());

  // Comando de válvula desde FastAPI o dashboard
  if (String(topic) == TOPIC_VALVULA) {
    if (msg == "ON"  || msg == "1") {
      digitalWrite(PIN_VALVULA, HIGH);
      Serial.println("💧 Válvula ABIERTA por comando remoto");
    } else if (msg == "OFF" || msg == "0") {
      digitalWrite(PIN_VALVULA, LOW);
      Serial.println("🔒 Válvula CERRADA por comando remoto");
    }
  }
}

// ══════════════════════════════════════════════════════════════════
// MQTT – CONEXIÓN
// ══════════════════════════════════════════════════════════════════
void conectarMQTT() {
  espClient.setInsecure();   // TLS sin verificar certificado raíz
                              // Para producción: usar espClient.setCACert(cert)
  mqttClient.setServer(mqtt_host, mqtt_port);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(60);
  mqttClient.setBufferSize(512);

  uint8_t intentos = 0;
  while (!mqttClient.connected() && intentos < 5) {
    Serial.print("Conectando MQTT...");
    if (mqttClient.connect(mqtt_client_id, mqtt_user, mqtt_password,
                           TOPIC_STATUS, 1, true, "offline")) {
      Serial.println("✅ MQTT conectado a HiveMQ");
      mqttClient.publish(TOPIC_STATUS, "online", true);  // LWT inverso
      mqttClient.subscribe(TOPIC_VALVULA);               // escuchar comandos
    } else {
      Serial.printf("❌ Error %d — reintentando...\n", mqttClient.state());
      delay(3000);
      intentos++;
    }
  }
}

// ══════════════════════════════════════════════════════════════════
// CÁLCULO HUMEDAD SUELO
// ══════════════════════════════════════════════════════════════════
float calcularHumedad(int adc) {
  if (adc >= ADC_SECO)   return 0.0f;
  if (adc <= ADC_MOJADO) return 100.0f;
  return constrain(
    100.0f - ((float)(adc - ADC_MOJADO) * 100.0f / (float)(ADC_SECO - ADC_MOJADO)),
    0.0f, 100.0f
  );
}

// ══════════════════════════════════════════════════════════════════
// TASK 1 – LECTURA DE SENSORES (Núcleo 1)
// ══════════════════════════════════════════════════════════════════
void taskSensores(void* parameter) {
  vTaskDelay(2000 / portTICK_PERIOD_MS);   // esperar estabilización

  while (true) {
    // Promedio de 5 lecturas ADC
    long suma = 0;
    for (int i = 0; i < 5; i++) {
      suma += analogRead(PIN_SUELO);
      vTaskDelay(10 / portTICK_PERIOD_MS);
    }
    int   adc_nuevo     = suma / 5;
    float humedad_nueva = calcularHumedad(adc_nuevo);

    ds18b20.requestTemperatures();
    float ts = ds18b20.getTempCByIndex(0);
    float ta = dht.readTemperature();
    float ha = dht.readHumidity();

    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      adc_suelo     = adc_nuevo;
      humedad_suelo = humedad_nueva;
      temp_suelo    = ts;
      temp_amb      = isnan(ta) ? temp_amb : ta;
      hum_amb       = isnan(ha) ? hum_amb  : ha;
      xSemaphoreGive(xMutex);
    }

    Serial.printf("📡 Suelo: ADC=%d  H=%.1f%%  Ts=%.1f°C  Ta=%.1f°C  Ha=%.1f%%\n",
                  adc_nuevo, humedad_nueva, ts, ta, ha);

    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

// ══════════════════════════════════════════════════════════════════
// TASK 2 – PUBLICACIÓN MQTT (Núcleo 0)
// ══════════════════════════════════════════════════════════════════
void taskMQTT(void* parameter) {
  vTaskDelay(7000 / portTICK_PERIOD_MS);   // esperar primera lectura

  while (true) {
    // Mantener conexión
    if (!mqttClient.connected()) {
      if (WiFi.status() != WL_CONNECTED) conectarWiFi();
      conectarMQTT();
    }
    mqttClient.loop();

    // Copiar variables de forma segura
    int   adc_c = 0; float hs_c = 0, ts_c = -127, ta_c = NAN, ha_c = NAN;
    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      adc_c = adc_suelo; hs_c = humedad_suelo;
      ts_c  = temp_suelo; ta_c = temp_amb; ha_c = hum_amb;
      xSemaphoreGive(xMutex);
    }

    // Construir JSON anidado compatible con RiegoDatosModel del backend
    StaticJsonDocument<512> doc;
    doc["device_id"] = mqtt_client_id;

    JsonObject hs = doc.createNestedObject("humedad_suelo");
    hs["sensor"] = "SUELO_1";
    hs["valor"] = round(hs_c * 100) / 100.0;
    hs["porcentaje"] = round(hs_c * 100) / 100.0;

    JsonObject ha = doc.createNestedObject("humedad_ambiente");
    ha["sensor"] = "DHT22";
    if (isnan(ha_c)) {
      ha["valor"] = nullptr;
      ha["porcentaje"] = nullptr;
    } else {
      ha["valor"] = round(ha_c * 100) / 100.0;
      ha["porcentaje"] = round(ha_c * 100) / 100.0;
    }

    JsonObject ta = doc.createNestedObject("temperatura_ambiente");
    ta["sensor"] = "DHT22";
    if (isnan(ta_c)) {
      ta["valor"] = nullptr;
      ta["temperatura"] = nullptr;
    } else {
      ta["valor"] = round(ta_c * 100) / 100.0;
      ta["temperatura"] = round(ta_c * 100) / 100.0;
    }

    JsonObject ts = doc.createNestedObject("temperatura_suelo");
    ts["sensor"] = "DS18B20";
    if (isnan(ts_c) || ts_c == -127) {
      ts["valor"] = nullptr;
      ts["temperatura"] = nullptr;
    } else {
      ts["valor"] = round(ts_c * 100) / 100.0;
      ts["temperatura"] = round(ts_c * 100) / 100.0;
    }

    doc["adc_raw"] = adc_c;

    char buffer[512];
    serializeJson(doc, buffer, sizeof(buffer));

    if (mqttClient.publish(TOPIC_SENSORES, buffer, false)) {
      Serial.println("📤 Publicado en MQTT:");
      Serial.println(buffer);
    } else {
      Serial.println("❌ Error al publicar en MQTT");
    }

    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

// ══════════════════════════════════════════════════════════════════
// SETUP
// ══════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== Yaku ESP32-S3 + MQTT HiveMQ ===");

  pinMode(PIN_VALVULA, OUTPUT);
  digitalWrite(PIN_VALVULA, LOW);   // válvula cerrada al inicio

  xMutex = xSemaphoreCreateMutex();
  if (!xMutex) {
    Serial.println("❌ Error creando mutex"); while (true) delay(1000);
  }

  conectarWiFi();
  conectarMQTT();

  dht.begin();
  ds18b20.begin();
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  xTaskCreatePinnedToCore(taskSensores, "Sensores", 4096, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(taskMQTT,     "MQTT",     8192, NULL, 1, NULL, 0);

  Serial.println("✅ Tareas iniciadas");
}

void loop() {
  vTaskDelay(portMAX_DELAY);
}
