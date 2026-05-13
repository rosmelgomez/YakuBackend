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
#define PIN_SUELO     4
#define DHTPIN        15
#define DHTTYPE       DHT22
#define ONE_WIRE_BUS  16
#define PIN_TRIG      17   // sensor de proximidad HC-SR04
#define PIN_ECHO      18   // sensor de proximidad HC-SR04
#define PIN_RELE      19   // bomba de agua

#define ALTURA_REFERENCIA_CM 20.0f

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
float distancia_ultima_valida = ALTURA_REFERENCIA_CM;
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

  if (!mqttClient.connected()) {
    conectarMQTT();
  }

  String json = "{";
  json += "\"sensor\":\"HC-SR04\",";
  json += "\"distancia_cm\":" + String(distancia_cm, 2) + ",";
  json += "\"altura_referencia_cm\":" + String(ALTURA_REFERENCIA_CM, 2) + ",";
  json += "\"estado_bomba\":\"" + estado_bomba + "\"";
  json += "}";

  bool ok = mqttClient.publish(mqtt_topic_control_agua, json.c_str(), true);
  if (ok) {
    Serial.print("📨 Control de agua publicado en ");
    Serial.println(mqtt_topic_control_agua);
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
    distancia_ultima_valida = distancia_actual;
  } else {
    distancia_actual = distancia_ultima_valida;
  }

  publicarControlAguaMQTT(distancia_actual, bomba_activa ? "ON" : "OFF");
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
// CÁLCULO HUMEDAD SUELO
// ══════════════════════════════════════════════════════════════════

// =====================================
// CÁLCULOS
// =====================================

float calcularHumedad(int adc) {
  if (adc >= ADC_SECO)   return 0.0f;
  if (adc <= ADC_MOJADO) return 100.0f;
  float porcentaje = 100.0f - ((float)(adc - ADC_MOJADO) * 100.0f / (float)(ADC_SECO - ADC_MOJADO));
  return constrain(porcentaje, 0.0f, 100.0f);
}

// =====================================
// TASK 1: LECTURA DE SENSORES (Núcleo 1)
// Stack 4096 es suficiente para lectura analógica + 1Wire + DHT
// =====================================

void taskSensores(void* parameter) {

  // Esperar que WiFi y radio se estabilicen antes de usar ADC
  vTaskDelay(2000 / portTICK_PERIOD_MS);

  while (true) {

    // Promediar 5 lecturas ADC para reducir ruido
    long suma = 0;
    for (int i = 0; i < 5; i++) {
      suma += analogRead(PIN_SUELO);
      vTaskDelay(10 / portTICK_PERIOD_MS);
    }
    int adc_nuevo = suma / 5;
    float humedad_nueva = calcularHumedad(adc_nuevo);

    // DS18B20
    ds18b20.requestTemperatures();
    float ts = ds18b20.getTempCByIndex(0);  // -127 si desconectado

    // DHT22 — puede tardar hasta 2s entre lecturas
    float ta = dht.readTemperature();
    float ha = dht.readHumidity();

    // --- Sección crítica: actualizar variables compartidas ---
    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      adc_suelo     = adc_nuevo;
      humedad_suelo = humedad_nueva;
      temp_suelo    = ts;
      temp_amb      = isnan(ta) ? temp_amb  : ta;  // Conservar último valor válido
      hum_amb       = isnan(ha) ? hum_amb   : ha;
      xSemaphoreGive(xMutex);
    }

    Serial.printf("📡 Suelo: ADC=%d  H=%.1f%%  Ts=%.1f°C  Ta=%.1f°C  Ha=%.1f%%\n",
                  adc_nuevo, humedad_nueva, ts, ta, ha);

    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

// =====================================
// TASK 2: ENVIO MQTT (Nucleo 0)
// Stack 8192 para red y publicacion
// =====================================

void taskEnvioDatos(void* parameter) {

  // Dar tiempo a taskSensores para obtener la primera lectura
  vTaskDelay(7000 / portTICK_PERIOD_MS);

  while (true) {

    if (WiFi.status() != WL_CONNECTED) conectarWiFi();
    if (!mqttClient.connected()) conectarMQTT();
    mqttClient.loop();

    // Copiar variables compartidas de forma segura
    int   adc_copia     = 0;
    float humedad_copia = 0;
    float ts_copia      = -127.0f;
    float ta_copia      = NAN;
    float ha_copia      = NAN;

    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      adc_copia     = adc_suelo;
      humedad_copia = humedad_suelo;
      ts_copia      = temp_suelo;
      ta_copia      = temp_amb;
      ha_copia      = hum_amb;
      xSemaphoreGive(xMutex);
    } else {
      Serial.println("⚠️ No se pudo obtener mutex para lectura. Saltando envío.");
      vTaskDelay(5000 / portTICK_PERIOD_MS);
      continue;
    }

    // Construir JSON con valores seguros (null si lectura inválida)
    String json = "{";
    json += "\"humedad_suelo\":{";
    json += "\"sensor\":\"suelo\",";
    json += "\"valor\":"      + String(adc_copia)              + ",";
    json += "\"porcentaje\":" + String(humedad_copia, 2);
    json += "},";

    json += "\"humedad_ambiente\":{";
    json += "\"sensor\":\"ambiente\",";
    json += "\"valor\":"      + floatSeguro(ha_copia) + ",";
    json += "\"porcentaje\":" + floatSeguro(ha_copia);
    json += "},";

    json += "\"temperatura_ambiente\":{";
    json += "\"sensor\":\"ambiente\",";
    json += "\"valor\":"        + floatSeguro(ta_copia) + ",";
    json += "\"temperatura\":" + floatSeguro(ta_copia);
    json += "},";

    json += "\"temperatura_suelo\":{";
    json += "\"sensor\":\"suelo\",";
    json += "\"valor\":"        + floatSeguro(ts_copia) + ",";
    json += "\"temperatura\":" + floatSeguro(ts_copia);
    json += "}";
    json += "}";

    publicarDatosMQTT(json);

    Serial.println("📤 JSON enviado:");
    Serial.println(json);

    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

// =====================================
// SETUP
// =====================================

void setup() {
  Serial.begin(115200);
  delay(1000); // Esperar que el monitor serie se conecte

  Serial.println("\n=== Sistema de Riego ESP32-S3 ===");

  // Crear mutex antes de lanzar tareas
  xMutex = xSemaphoreCreateMutex();
  if (xMutex == NULL) {
    Serial.println("❌ Error fatal: no se pudo crear el mutex.");
    while (true) { delay(1000); } // Detener ejecución
  }

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_RELE, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  digitalWrite(PIN_RELE, LOW);

  conectarWiFi();
  wifiClient.setCACert(mqtt_ca_cert);
  mqttClient.setServer(mqtt_host, mqtt_port);

  dht.begin();
  ds18b20.begin();

  // ESP32-S3 tiene ADC de 12 bits (0-4095)
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db); // Rango 0-3.3V (necesario para lecturas completas)

  // Crear tareas en núcleos diferentes
  // xTaskCreatePinnedToCore(función, nombre, stack_words, param, prioridad, handle, núcleo)
  xTaskCreatePinnedToCore(taskSensores,   "Sensores",   4096, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(taskEnvioDatos, "EnvioDatos", 8192, NULL, 1, NULL, 0);

  Serial.println("✅ Tareas iniciadas");
}

// =====================================
// LOOP VACÍO (FreeRTOS gestiona todo)
// =====================================

void loop() {
  vTaskDelay(portMAX_DELAY); // Ceder CPU completamente
}
