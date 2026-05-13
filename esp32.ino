/*
  ============================================================
  SISTEMA DE RIEGO – ESP32 + MQTT HiveMQ Cloud
  Broker : 85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud
  Puerto : 8883 (TLS)
  ============================================================
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ── WiFi ──────────────────────────────────────────────────────────
const char* ssid     = "HGB_2,4GHz";
const char* password = "@Hgb153427986@";

// ── HiveMQ Cloud ──────────────────────────────────────────────────
const char* mqtt_host     = "85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud";
const uint16_t mqtt_port  = 8883;
const char* mqtt_user     = "hivemq.webclient.1778630712813";
const char* mqtt_password = "pVA$d1KU,>R7gM30b@vo";
const char* mqtt_client_id = "ESP32_Yaku_002";

// ── Topics ────────────────────────────────────────────────────────
const char* TOPIC_SENSORES  = "yaku/riego/datos";
const char* TOPIC_CONTROL_CMD = "yaku/riego/comando";
const char* TOPIC_CONTROL_AGUA = "yaku/riego/control_agua";
const char* TOPIC_STATUS    = "yaku/status";

// ── Clientes MQTT ─────────────────────────────────────────────────
WiFiClientSecure espClient;
PubSubClient     mqttClient(espClient);

// ── Pines ─────────────────────────────────────────────────────────
#define PIN_TRIG      17   // sensor de proximidad HC-SR04 (TRIG)
#define PIN_ECHO      18   // sensor de proximidad HC-SR04 (ECHO)
#define PIN_RELE      19   // bomba de agua (relé)

#define ALTURA_REFERENCIA_CM 20.0f

// ── Variables compartidas ─────────────────────────────────────────
SemaphoreHandle_t xMutex;
float distancia_cm = ALTURA_REFERENCIA_CM;
bool bomba_activa = false;

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

float leerDistanciaCM() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long duracion = pulseIn(PIN_ECHO, HIGH, 30000);
  if (duracion == 0) {
    return NAN;
  }

  return (duracion * 0.0343f) / 2.0f;
}

void publicarControlAguaMQTT(float distancia_cm, const String& estado_bomba) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi no conectado. No se puede guardar control de agua.");
    return;
  }
  if (!mqttClient.connected()) conectarMQTT();

  String json = "{";
  json += "\"sensor\":\"HC-SR04\",";
  json += "\"distancia_cm\":" + String(distancia_cm, 2) + ",";
  json += "\"altura_referencia_cm\":" + String(ALTURA_REFERENCIA_CM, 2) + ",";
  json += "\"estado_bomba\":\"" + estado_bomba + "\"";
  json += "}";

  bool ok = mqttClient.publish(TOPIC_CONTROL_AGUA, json.c_str(), true);
  if (ok) {
    Serial.print("📨 Control de agua publicado en ");
    Serial.println(TOPIC_CONTROL_AGUA);
    Serial.println(json);
  } else {
    Serial.println("❌ Error al publicar control de agua");
  }
}

void manejarComandoBomba(const String& comando) {
  String comando_normalizado = comando;
  comando_normalizado.toUpperCase();

  if (comando_normalizado == "ON" || comando_normalizado == "1") {
    bomba_activa = true;
    digitalWrite(PIN_RELE, HIGH);
    Serial.println("💧 Bomba activada por ML");
  } else if (comando_normalizado == "OFF" || comando_normalizado == "0") {
    bomba_activa = false;
    digitalWrite(PIN_RELE, LOW);
    Serial.println("🔒 Bomba desactivada por ML");
  } else {
    Serial.print("⚠️ Comando no reconocido: ");
    Serial.println(comando);
    return;
  }

  float distancia_actual = leerDistanciaCM();
  if (!isnan(distancia_actual)) {
    distancia_cm = distancia_actual;
  }

  publicarControlAguaMQTT(distancia_cm, bomba_activa ? "ON" : "OFF");
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.printf("📥 [%s] %s\n", topic, msg.c_str());
  if (String(topic) == TOPIC_CONTROL_CMD) {
    manejarComandoBomba(msg);
  }
}

// ══════════════════════════════════════════════════════════════════
// MQTT – CONEXIÓN
// ══════════════════════════════════════════════════════════════════
void conectarMQTT() {
  espClient.setInsecure();
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
      mqttClient.publish(TOPIC_STATUS, "online", true);
      mqttClient.subscribe(TOPIC_CONTROL_CMD);
    } else {
      Serial.printf("❌ Error %d — reintentando...\n", mqttClient.state());
      delay(3000);
      intentos++;
    }
  }
}



// ══════════════════════════════════════════════════════════════════
// TASK 1 – LECTURA DE PROFUNDIDAD (Núcleo 1)
// ══════════════════════════════════════════════════════════════════
void taskSensores(void* parameter) {
  vTaskDelay(2000 / portTICK_PERIOD_MS);

  while (true) {
    float distancia = leerDistanciaCM();

    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      if (!isnan(distancia)) {
        distancia_cm = distancia;
      }
      xSemaphoreGive(xMutex);
    }

    Serial.printf("📡 Profundidad: %.2f cm\n", distancia_cm);

    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

// ══════════════════════════════════════════════════════════════════
// TASK 2 – PUBLICACIÓN MQTT (Núcleo 0)
// ══════════════════════════════════════════════════════════════════
void taskMQTT(void* parameter) {
  vTaskDelay(7000 / portTICK_PERIOD_MS);

  while (true) {
    if (!mqttClient.connected()) {
      if (WiFi.status() != WL_CONNECTED) conectarWiFi();
      conectarMQTT();
    }
    mqttClient.loop();

    float dist_c = ALTURA_REFERENCIA_CM;
    bool bomba_c = false;
    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      dist_c = distancia_cm;
      bomba_c = bomba_activa;
      xSemaphoreGive(xMutex);
    }

    StaticJsonDocument<256> doc;
    doc["device_id"] = mqtt_client_id;
    doc["sensor"] = "HC-SR04";
    doc["distancia_cm"] = round(dist_c * 100) / 100.0;
    doc["altura_referencia_cm"] = ALTURA_REFERENCIA_CM;
    doc["bomba"] = bomba_c ? "ON" : "OFF";
    doc["timestamp"] = millis();

    char buffer[256];
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
  Serial.println("\n=== Yaku ESP32 Proximity + Pump ===");

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_RELE, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  digitalWrite(PIN_RELE, LOW);

  xMutex = xSemaphoreCreateMutex();
  if (!xMutex) {
    Serial.println("❌ Error creando mutex"); while (true) delay(1000);
  }

  conectarWiFi();
  conectarMQTT();

  xTaskCreatePinnedToCore(taskSensores, "Sensores", 4096, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(taskMQTT,     "MQTT",     8192, NULL, 1, NULL, 0);

  Serial.println("✅ Tareas iniciadas");
}

void loop() {
  vTaskDelay(portMAX_DELAY);
}
