  /*
  ============================================================
  SISTEMA DE RIEGO - ESP32-S3
  Versión mejorada con:
  - Mutex para variables compartidas entre tareas
  - Pines compatibles con ESP32-S3
  - Protección contra lecturas NaN/inválidas del DHT22
  - Stack size aumentado para mayor estabilidad
  - Reconexión WiFi robusta
  - JSON seguro con valores de fallback
  ============================================================
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// =====================================
// WIFI + MQTT
// =====================================

const char* ssid     = "HGB_2,4GHz";
const char* password = "@Hgb153427986@";

const char* mqtt_host = "85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud";
const uint16_t mqtt_port = 8883;
const char* mqtt_topic_riego = "yaku/riego/datos";
const char* mqtt_user = "CAMBIA_TU_USUARIO_HIVEMQ";
const char* mqtt_password = "CAMBIA_TU_PASSWORD_HIVEMQ";

static const char* mqtt_ca_cert = R"EOF(
-----BEGIN CERTIFICATE-----

-----END CERTIFICATE-----
)EOF";

WiFiClientSecure wifiClient;
PubSubClient mqttClient(wifiClient);

// =====================================
// PINES - Compatible con ESP32-S3
// NOTA: En ESP32-S3 el ADC2 no funciona con WiFi activo.
//       Se usan pines ADC1 (GPIO 1-10, 11-20 en S3).
//       GPIO 4  → ADC seguro en ESP32-S3 (ADC1_CH3)
//       GPIO 15 → DHT22 (GPIO digital OK)
//       GPIO 16 → DS18B20 (GPIO digital OK)
// =====================================

#define PIN_SUELO   4   // ADC1_CH3 — seguro con WiFi
#define DHTPIN      15  // DHT22
#define DHTTYPE     DHT22
#define ONE_WIRE_BUS 16 // DS18B20

// Calibración del sensor capacitivo de humedad de suelo
// Ajusta estos valores según tu sensor específico (medidos en seco y en agua)
#define ADC_SECO   3200  // Valor ADC en aire/seco  (antes: 4095 — muy extremo)
#define ADC_MOJADO 1200  // Valor ADC sumergido en agua

// =====================================
// SENSORES
// =====================================

DHT dht(DHTPIN, DHTTYPE);
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);

// =====================================
// VARIABLES COMPARTIDAS + MUTEX
// El mutex evita que taskEnvioDatos lea datos
// a mitad de una escritura de taskSensores.
// =====================================

SemaphoreHandle_t xMutex;

int   adc_suelo     = 0;
float humedad_suelo = 0.0f;
float temp_suelo    = -127.0f;  // DS18B20 devuelve -127 si hay error
float temp_amb      = NAN;
float hum_amb       = NAN;

// =====================================
// WIFI
// =====================================

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("Conectando WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  uint8_t intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(1000);
    Serial.print(".");
    intentos++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi conectado: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n❌ No se pudo conectar al WiFi. Reintentando en el próximo ciclo.");
  }
}

// =====================================
// MQTT
// =====================================

// Convierte float a string; devuelve "null" si es NaN o error de sensor
String floatSeguro(float valor, int decimales = 2) {
  if (isnan(valor) || valor == -127.0f) return "null";
  return String(valor, decimales);
}

void conectarMQTT() {
  if (mqttClient.connected()) return;

  Serial.println("Conectando MQTT...");
  while (!mqttClient.connected()) {
    String clientId = "esp32-riego-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqttClient.connect(clientId.c_str(), mqtt_user, mqtt_password)) {
      Serial.println("✅ MQTT conectado");
    } else {
      Serial.print("❌ MQTT error, rc=");
      Serial.println(mqttClient.state());
      delay(3000);
    }
  }
}

void publicarDatosMQTT(const String& json) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi no conectado. Saltando publicacion.");
    return;
  }

  if (!mqttClient.connected()) {
    conectarMQTT();
  }

  bool ok = mqttClient.publish(mqtt_topic_riego, json.c_str(), true);
  if (ok) {
    Serial.print("📨 MQTT publicado en ");
    Serial.println(mqtt_topic_riego);
  } else {
    Serial.println("❌ Error al publicar en MQTT");
  }
}

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
