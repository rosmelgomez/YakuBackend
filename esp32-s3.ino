/*
  ============================================================
  SISTEMA DE RIEGO - ESP32-S3 + MQTT HiveMQ Cloud v2.0
  Mejoras de precision:
  - ADC: 20 muestras con filtro de mediana + eliminacion outliers
  - DHT22: promedio de 3 lecturas validas con timeout
  - DS18B20: resolucion 12 bits (0.0625C) + validacion de rango
  - Filtro EMA (media movil exponencial) para suavizar ruido
  - Estadisticas de calidad por sensor (min, max, desviacion)
  ============================================================
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <algorithm>   // std::sort para mediana

// ── WiFi ──────────────────────────────────────────────────────────
// ── HiveMQ Cloud ──────────────────────────────────────────────────
String wifiSsid = "";
String wifiPassword = "";
String mqttHost = "85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud";
uint16_t mqttPort = 8883;
String mqttUser = "";
String mqttPassword = "";
String mqttClientId = "YAKU-S3-UNPROVISIONED";

// ── Topics ────────────────────────────────────────────────────────
String topicSensores = "yaku/riego/datos";
const char* TOPIC_STATUS   = "yaku/status";

// ── Pines ─────────────────────────────────────────────────────────
#define PIN_SUELO     17
#define DHTPIN        15
#define DHTTYPE       DHT22
#define ONE_WIRE_BUS  16

// ── Calibración sensor capacitivo de suelo ────────────────────────
// Ajusta midiendo tu sensor en aire seco y sumergido en agua
#define ADC_SECO        4095
#define ADC_MOJADO      2055

// ── Parámetros de precisión ───────────────────────────────────────
#define ADC_MUESTRAS        20     // Muestras ADC por lectura
#define ADC_DESCARTE         4     // Descartar N valores extremos (outliers)
#define DHT_REINTENTOS       5     // Intentos máximos de lectura DHT22
#define DHT_DELAY_MS       300     // Espera entre intentos DHT22 (ms)
#define EMA_ALPHA         0.25f    // Factor filtro EMA (0.1=suave, 0.5=rápido)

// ── Rangos válidos para validación ───────────────────────────────
const uint32_t INTERVALO_CAPTURA_MS = 60000;
const uint32_t INTERVALO_PUBLICACION_MS = 60000;

#define TEMP_MIN          -10.0f
#define TEMP_MAX           60.0f
#define HUM_MIN             0.0f
#define HUM_MAX           100.0f
#define TEMP_SUELO_MIN    -10.0f
#define TEMP_SUELO_MAX     50.0f

// ── Objetos sensores ──────────────────────────────────────────────
DHT dht(DHTPIN, DHTTYPE);
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);

// ── Estado del sensor (calidad de lectura) ────────────────────────
struct SensorStats {
  float valor;         // Valor filtrado actual
  float ema;           // Valor EMA (suavizado)
  float minVal;        // Mínimo histórico de sesión
  float maxVal;        // Máximo histórico de sesión
  float desviacion;    // Desviación estándar de última tanda
  bool  valido;        // Lectura válida o no
  uint16_t errores;    // Contador de errores acumulados
};

// ── Variables compartidas ─────────────────────────────────────────
SemaphoreHandle_t xMutex;

// ── IDs de Asignación en la Base de Datos ───────────────────────────
int id_asignacion_humedad_suelo = 0;
int id_asignacion_humedad_ambiente = 0;
int id_asignacion_temperatura_ambiente = 0;
int id_asignacion_temperatura_suelo = 0;

SensorStats s_humSuelo  = {0, 0, 100, 0, 0, false, 0};
SensorStats s_tempSuelo = {-127, -127, 100, -127, 0, false, 0};
SensorStats s_tempAmb   = {NAN, NAN, 100, -100, 0, false, 0};
SensorStats s_humAmb    = {NAN, NAN, 100, 0, 0, false, 0};
int         adc_raw     = 0;
bool        funcionamientoActivo = false;

// ── Clientes MQTT ─────────────────────────────────────────────────
WiFiClientSecure espClient;
PubSubClient     mqttClient(espClient);
Preferences preferences;
String serialBuffer;

void guardarConfiguracion() {
  preferences.begin("yaku", false);
  preferences.putString("wifi_ssid", wifiSsid);
  preferences.putString("wifi_pass", wifiPassword);
  preferences.putString("mqtt_host", mqttHost);
  preferences.putUShort("mqtt_port", mqttPort);
  preferences.putString("mqtt_user", mqttUser);
  preferences.putString("mqtt_pass", mqttPassword);
  preferences.putString("client_id", mqttClientId);
  preferences.putString("topic_pub", topicSensores);
  preferences.putInt("asig_hs", id_asignacion_humedad_suelo);
  preferences.putInt("asig_ha", id_asignacion_humedad_ambiente);
  preferences.putInt("asig_ta", id_asignacion_temperatura_ambiente);
  preferences.putInt("asig_ts", id_asignacion_temperatura_suelo);
  preferences.end();
}

void cargarConfiguracion() {
  preferences.begin("yaku", true);
  wifiSsid = preferences.getString("wifi_ssid", wifiSsid);
  wifiPassword = preferences.getString("wifi_pass", wifiPassword);
  mqttHost = preferences.getString("mqtt_host", mqttHost);
  mqttPort = preferences.getUShort("mqtt_port", mqttPort);
  mqttUser = preferences.getString("mqtt_user", mqttUser);
  mqttPassword = preferences.getString("mqtt_pass", mqttPassword);
  mqttClientId = preferences.getString("client_id", mqttClientId);
  topicSensores = preferences.getString("topic_pub", topicSensores);
  id_asignacion_humedad_suelo = preferences.getInt("asig_hs", 0);
  id_asignacion_humedad_ambiente = preferences.getInt("asig_ha", 0);
  id_asignacion_temperatura_ambiente = preferences.getInt("asig_ta", 0);
  id_asignacion_temperatura_suelo = preferences.getInt("asig_ts", 0);
  preferences.end();
}

bool configuracionCompleta() {
  return wifiSsid.length() > 0 && wifiPassword.length() > 0 &&
         mqttHost.length() > 0 && mqttPort > 0 &&
         mqttUser.length() > 0 && mqttPassword.length() > 0 &&
         mqttClientId.length() > 0 &&
         id_asignacion_humedad_suelo > 0 &&
         id_asignacion_humedad_ambiente > 0 &&
         id_asignacion_temperatura_ambiente > 0 &&
         id_asignacion_temperatura_suelo > 0;
}

bool aplicarProvisionamiento(const String& json) {
  DynamicJsonDocument doc(2048);
  DeserializationError jsonError = deserializeJson(doc, json);
  if (jsonError) {
    Serial.printf("YAKU_CONFIG_JSON_ERROR: %s\n", jsonError.c_str());
    return false;
  }
  if (!doc.containsKey("device_uid") || !doc.containsKey("wifi") ||
      !doc.containsKey("mqtt") || !doc.containsKey("asignaciones")) {
    Serial.println("YAKU_CONFIG_MISSING_SECTIONS");
    return false;
  }
  mqttClientId = doc["device_uid"].as<String>();
  JsonObject wifi = doc["wifi"];
  JsonObject mqtt = doc["mqtt"];
  JsonObject asig = doc["asignaciones"];
  if (!wifi.isNull()) {
    if (wifi.containsKey("ssid")) wifiSsid = wifi["ssid"].as<String>();
    if (wifi.containsKey("password")) wifiPassword = wifi["password"].as<String>();
  }
  if (!mqtt.isNull()) {
    if (mqtt.containsKey("host")) mqttHost = mqtt["host"].as<String>();
    mqttPort = mqtt["port"] | mqttPort;
    if (mqtt.containsKey("username")) mqttUser = mqtt["username"].as<String>();
    if (mqtt.containsKey("password")) mqttPassword = mqtt["password"].as<String>();
    if (mqtt.containsKey("topic_pub") && !mqtt["topic_pub"].isNull()) topicSensores = mqtt["topic_pub"].as<String>();
  }
  id_asignacion_humedad_suelo = asig["HUM_SUELO"] | 0;
  id_asignacion_humedad_ambiente = asig["HUM_AMB"] | 0;
  id_asignacion_temperatura_ambiente = asig["TEMP_AMB"] | 0;
  id_asignacion_temperatura_suelo = asig["TEMP_SUELO"] | 0;
  if (!configuracionCompleta()) {
    Serial.println("YAKU_CONFIG_INCOMPLETE");
    return false;
  }
  guardarConfiguracion();
  return true;
}

void procesarProvisionamientoSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      serialBuffer.trim();
      if (serialBuffer.length() > 0) {
        if (aplicarProvisionamiento(serialBuffer)) {
          Serial.println("YAKU_PROVISIONING_OK");
          delay(300);
          ESP.restart();
        } else {
          Serial.println("YAKU_PROVISIONING_ERROR");
        }
      }
      serialBuffer = "";
    } else if (serialBuffer.length() < 4096) {
      serialBuffer += c;
    }
  }
}


// ══════════════════════════════════════════════════════════════════
// UTILIDADES DE PRECISIÓN
// ══════════════════════════════════════════════════════════════════

// Mediana de un arreglo (modifica una copia interna)
float mediana(int* arr, int n) {
  int tmp[n];
  memcpy(tmp, arr, n * sizeof(int));
  std::sort(tmp, tmp + n);
  return (n % 2 == 0)
    ? (tmp[n/2 - 1] + tmp[n/2]) / 2.0f
    : (float)tmp[n/2];
}

// Desviación estándar de un arreglo de floats
float desviacionEstandar(float* arr, int n, float media) {
  float suma = 0;
  for (int i = 0; i < n; i++) suma += (arr[i] - media) * (arr[i] - media);
  return sqrt(suma / n);
}

// Filtro EMA — suaviza ruido manteniendo respuesta ante cambios reales
float aplicarEMA(float valorNuevo, float emaAnterior, float alpha) {
  if (isnan(emaAnterior)) return valorNuevo;
  return alpha * valorNuevo + (1.0f - alpha) * emaAnterior;
}

// Redondear a N decimales
float redondear(float val, int decimales) {
  float factor = pow(10, decimales);
  return round(val * factor) / factor;
}

// Validar que un valor esté en rango físico esperado
bool enRango(float val, float minV, float maxV) {
  return !isnan(val) && val >= minV && val <= maxV;
}


// ══════════════════════════════════════════════════════════════════
// LECTURA ADC – HUMEDAD DE SUELO (alta precisión)
// ══════════════════════════════════════════════════════════════════
void leerSueloADC(SensorStats& s) {
  int muestras[ADC_MUESTRAS];

  // 1. Tomar ADC_MUESTRAS lecturas con pausa entre ellas
  for (int i = 0; i < ADC_MUESTRAS; i++) {
    muestras[i] = analogRead(PIN_SUELO);
    vTaskDelay(8 / portTICK_PERIOD_MS);  // 8ms entre muestras
  }

  // 2. Ordenar para filtrado
  int tmp[ADC_MUESTRAS];
  memcpy(tmp, muestras, sizeof(muestras));
  std::sort(tmp, tmp + ADC_MUESTRAS);

  // 3. Calcular media descartando extremos (outliers)
  int n_validos = ADC_MUESTRAS - ADC_DESCARTE * 2;
  long suma = 0;
  float vals[n_validos];
  for (int i = ADC_DESCARTE; i < ADC_MUESTRAS - ADC_DESCARTE; i++) {
    suma += tmp[i];
    vals[i - ADC_DESCARTE] = (float)tmp[i];
  }
  float media_adc = (float)suma / n_validos;

  // 4. Calcular desviación estándar de la tanda
  s.desviacion = desviacionEstandar(vals, n_validos, media_adc);

  // 5. Convertir ADC → porcentaje de humedad
  float humedad;
  if (media_adc >= ADC_SECO)        humedad = 0.0f;
  else if (media_adc <= ADC_MOJADO) humedad = 100.0f;
  else humedad = 100.0f - ((media_adc - ADC_MOJADO) * 100.0f / (ADC_SECO - ADC_MOJADO));
  humedad = constrain(humedad, 0.0f, 100.0f);

  // 6. Aplicar EMA
  s.ema   = aplicarEMA(humedad, s.ema, EMA_ALPHA);
  s.valor = redondear(s.ema, 2);
  adc_raw = (int)round(media_adc);

  // 7. Actualizar min/max
  if (s.valor < s.minVal) s.minVal = s.valor;
  if (s.valor > s.maxVal) s.maxVal = s.valor;
  s.valido = true;

  Serial.printf("  [Suelo] ADC bruto=%.0f | σ=%.1f | H=%.2f%% | EMA=%.2f%%\n",
                media_adc, s.desviacion, humedad, s.ema);
}


// ══════════════════════════════════════════════════════════════════
// LECTURA DS18B20 – TEMPERATURA DE SUELO (12 bits)
// ══════════════════════════════════════════════════════════════════
void leerDS18B20(SensorStats& s) {
  // Asegurar resolución máxima (12 bits = 0.0625°C)
  ds18b20.setResolution(12);
  ds18b20.setWaitForConversion(false);  // no bloquear, esperamos manualmente

  ds18b20.requestTemperatures();
  vTaskDelay(750 / portTICK_PERIOD_MS);  // 750ms para resolución 12 bits

  float t = ds18b20.getTempCByIndex(0);

  // Validar: DS18B20 devuelve -127 si está desconectado, 85°C si no inicializó
  if (t == -127.0f || t == 85.0f || !enRango(t, TEMP_SUELO_MIN, TEMP_SUELO_MAX)) {
    s.valido = false;
    s.errores++;
    Serial.printf("  [DS18B20] ❌ Lectura inválida: %.2f°C (error #%d)\n", t, s.errores);
    return;
  }

  // Aplicar EMA
  s.ema   = aplicarEMA(t, s.ema == -127 ? t : s.ema, EMA_ALPHA);
  s.valor = redondear(s.ema, 2);

  if (s.valor < s.minVal || s.minVal == 100) s.minVal = s.valor;
  if (s.valor > s.maxVal || s.maxVal == -127) s.maxVal = s.valor;
  s.valido  = true;
  s.errores = 0;

  Serial.printf("  [DS18B20] %.4f°C → EMA=%.2f°C (min=%.2f max=%.2f)\n",
                t, s.ema, s.minVal, s.maxVal);
}


// ══════════════════════════════════════════════════════════════════
// LECTURA DHT22 – TEMPERATURA Y HUMEDAD AMBIENTE
// ══════════════════════════════════════════════════════════════════
void leerDHT22(SensorStats& sTemp, SensorStats& sHum) {
  float temps[DHT_REINTENTOS], hums[DHT_REINTENTOS];
  int   n_temp = 0, n_hum = 0;

  for (int i = 0; i < DHT_REINTENTOS; i++) {
    float t = dht.readTemperature();
    float h = dht.readHumidity();

    if (enRango(t, TEMP_MIN, TEMP_MAX))  temps[n_temp++] = t;
    if (enRango(h, HUM_MIN,  HUM_MAX))   hums[n_hum++]  = h;

    if (n_temp >= 3 && n_hum >= 3) break;  // 3 lecturas válidas son suficientes
    vTaskDelay(DHT_DELAY_MS / portTICK_PERIOD_MS);
  }

  // ── Temperatura ambiente ──────────────────────────────────────
  if (n_temp > 0) {
    float suma = 0;
    for (int i = 0; i < n_temp; i++) suma += temps[i];
    float media = suma / n_temp;

    sTemp.desviacion = (n_temp > 1) ? desviacionEstandar(temps, n_temp, media) : 0;
    sTemp.ema        = aplicarEMA(media, isnan(sTemp.ema) ? media : sTemp.ema, EMA_ALPHA);
    sTemp.valor      = redondear(sTemp.ema, 2);
    if (sTemp.valor < sTemp.minVal || sTemp.minVal == 100) sTemp.minVal = sTemp.valor;
    if (sTemp.valor > sTemp.maxVal) sTemp.maxVal = sTemp.valor;
    sTemp.valido  = true;
    sTemp.errores = 0;
    Serial.printf("  [DHT22-T] %d lecturas válidas | media=%.2f°C | σ=%.3f | EMA=%.2f°C\n",
                  n_temp, media, sTemp.desviacion, sTemp.ema);
  } else {
    sTemp.valido = false;
    sTemp.errores++;
    Serial.printf("  [DHT22-T] ❌ Sin lecturas válidas (error #%d)\n", sTemp.errores);
  }

  // ── Humedad ambiente ──────────────────────────────────────────
  if (n_hum > 0) {
    float suma = 0;
    for (int i = 0; i < n_hum; i++) suma += hums[i];
    float media = suma / n_hum;

    sHum.desviacion = (n_hum > 1) ? desviacionEstandar(hums, n_hum, media) : 0;
    sHum.ema        = aplicarEMA(media, isnan(sHum.ema) ? media : sHum.ema, EMA_ALPHA);
    sHum.valor      = redondear(sHum.ema, 2);
    if (sHum.valor < sHum.minVal || sHum.minVal == 100) sHum.minVal = sHum.valor;
    if (sHum.valor > sHum.maxVal) sHum.maxVal = sHum.valor;
    sHum.valido  = true;
    sHum.errores = 0;
    Serial.printf("  [DHT22-H] %d lecturas válidas | media=%.2f%% | σ=%.3f | EMA=%.2f%%\n",
                  n_hum, media, sHum.desviacion, sHum.ema);
  } else {
    sHum.valido = false;
    sHum.errores++;
    Serial.printf("  [DHT22-H] ❌ Sin lecturas válidas (error #%d)\n", sHum.errores);
  }
}


// ══════════════════════════════════════════════════════════════════
// WIFI
// ══════════════════════════════════════════════════════════════════
void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.println("Conectando WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
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
// MQTT
// ══════════════════════════════════════════════════════════════════
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.printf("📥 [%s] %s\n", topic, msg.c_str());

  String topicStr = String(topic);
  String configTopic = "yaku/dispositivo/" + mqttClientId + "/config";

  if (topicStr == configTopic) {
    msg.trim();
    DynamicJsonDocument doc(1536);
    if (!deserializeJson(doc, msg)) {
      if (doc.containsKey("funcionamiento_activo")) funcionamientoActivo = doc["funcionamiento_activo"];
      JsonObject asig = doc["asignaciones"];
      if (!asig.isNull()) {
        id_asignacion_humedad_suelo = asig["HUM_SUELO"] | id_asignacion_humedad_suelo;
        id_asignacion_humedad_ambiente = asig["HUM_AMB"] | id_asignacion_humedad_ambiente;
        id_asignacion_temperatura_ambiente = asig["TEMP_AMB"] | id_asignacion_temperatura_ambiente;
        id_asignacion_temperatura_suelo = asig["TEMP_SUELO"] | id_asignacion_temperatura_suelo;
        guardarConfiguracion();
      }
      return;
    }
    msg.toUpperCase();
    if (msg == "INACTIVE" || msg == "0" || msg == "OFF" || msg == "CAPTURE_OFF") {
      funcionamientoActivo = false;
      Serial.println("⚙️ Funcionamiento DESACTIVADO por el usuario");
    } else if (msg == "ACTIVE" || msg == "1" || msg == "ON" || msg == "CAPTURE_ON") {
      funcionamientoActivo = true;
      Serial.println("⚙️ Funcionamiento ACTIVADO por el usuario");
    }
  }
}

void conectarMQTT() {
  espClient.setInsecure();
  mqttClient.setServer(mqttHost.c_str(), mqttPort);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(60);
  mqttClient.setBufferSize(768);  // más espacio para JSON con estadísticas

  uint8_t intentos = 0;
  while (!mqttClient.connected() && intentos < 5) {
    Serial.print("Conectando MQTT...");
    if (mqttClient.connect(mqttClientId.c_str(), mqttUser.c_str(), mqttPassword.c_str(),
                           TOPIC_STATUS, 1, true, "offline")) {
      Serial.println("✅ MQTT conectado a HiveMQ");
      mqttClient.publish(TOPIC_STATUS, "online", true);

      String configTopic = "yaku/dispositivo/" + mqttClientId + "/config";
      mqttClient.subscribe(configTopic.c_str());
      Serial.printf("   Suscrito a config: %s\n", configTopic.c_str());
      String reqTopic = "yaku/dispositivo/" + mqttClientId + "/config/req";
      String reqPayload = "{\"client_id\":\"" + mqttClientId + "\"}";
      mqttClient.publish(reqTopic.c_str(), reqPayload.c_str());
    } else {
      Serial.printf("❌ Error %d\n", mqttClient.state());
      delay(3000);
      intentos++;
    }
  }
}


// ══════════════════════════════════════════════════════════════════
// TASK 1 – LECTURA DE SENSORES (Núcleo 1)
// ══════════════════════════════════════════════════════════════════
void taskSensores(void* parameter) {
  vTaskDelay(2000 / portTICK_PERIOD_MS);

  while (true) {
    if (!funcionamientoActivo) {
      vTaskDelay(1000 / portTICK_PERIOD_MS);
      continue;
    }
    Serial.println("\n── Ciclo de lectura ──────────────────────");

    // Lecturas locales antes de tomar el mutex
    SensorStats hs_local, ts_local, ta_local, ha_local;
    int adc_local;

    // Copiar EMA actuales para continuar el filtro
    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(500)) == pdTRUE) {
      hs_local = s_humSuelo;
      ts_local = s_tempSuelo;
      ta_local = s_tempAmb;
      ha_local = s_humAmb;
      xSemaphoreGive(xMutex);
    }

    // Lecturas (fuera del mutex para no bloquear la publicación)
    leerSueloADC(hs_local);
    leerDS18B20(ts_local);
    leerDHT22(ta_local, ha_local);

    // Actualizar variables compartidas
    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      s_humSuelo  = hs_local;
      s_tempSuelo = ts_local;
      s_tempAmb   = ta_local;
      s_humAmb    = ha_local;
      xSemaphoreGive(xMutex);
    }

    Serial.printf("✅ H.Suelo=%.2f%% T.Suelo=%.2f°C T.Amb=%.2f°C H.Amb=%.2f%%\n",
                  hs_local.valor, ts_local.valor, ta_local.valor, ha_local.valor);

    // Espera interrumpible para responder a ACTIVE/INACTIVE.
    uint32_t espera = 0;
    while (funcionamientoActivo && espera < INTERVALO_CAPTURA_MS) {
      vTaskDelay(100 / portTICK_PERIOD_MS);
      espera += 100;
    }
  }
}


// ══════════════════════════════════════════════════════════════════
// TASK 2 – PUBLICACIÓN MQTT (Núcleo 0)
// ══════════════════════════════════════════════════════════════════
void taskMQTT(void* parameter) {
  vTaskDelay(10000 / portTICK_PERIOD_MS);  // esperar primera lectura completa
  uint32_t ultimaPublicacion = 0;

  while (true) {
    if (!configuracionCompleta()) {
      vTaskDelay(1000 / portTICK_PERIOD_MS);
      continue;
    }
    if (!mqttClient.connected()) {
      if (WiFi.status() != WL_CONNECTED) conectarWiFi();
      conectarMQTT();
    }
    mqttClient.loop();

    if (!funcionamientoActivo) {
      vTaskDelay(100 / portTICK_PERIOD_MS);
      continue;
    }

    uint32_t ahora = millis();
    if (ultimaPublicacion != 0 && ahora - ultimaPublicacion < INTERVALO_PUBLICACION_MS) {
      vTaskDelay(50 / portTICK_PERIOD_MS);
      continue;
    }

    // Copiar datos de forma segura
    SensorStats hs, ts, ta, ha;
    int raw_adc;
    if (xSemaphoreTake(xMutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
      hs = s_humSuelo; ts = s_tempSuelo;
      ta = s_tempAmb;  ha = s_humAmb;
      raw_adc = adc_raw;
      xSemaphoreGive(xMutex);
    }

    // Construir JSON con valores EMA + estadísticas de calidad
    StaticJsonDocument<512> doc;

    // humedad_suelo
    JsonObject j_hs = doc.createNestedObject("humedad_suelo");
    j_hs["id_asignacion"] = id_asignacion_humedad_suelo;
    j_hs["valor"]         = hs.valor;
    j_hs["porcentaje"]    = hs.valor;
    j_hs["ema"]           = redondear(hs.ema, 2);
    j_hs["desviacion"]    = redondear(hs.desviacion, 2);
    j_hs["valido"]        = hs.valido;

    // humedad_ambiente
    JsonObject j_ha = doc.createNestedObject("humedad_ambiente");
    j_ha["id_asignacion"] = id_asignacion_humedad_ambiente;
    if (!ha.valido) {
      j_ha["valor"] = nullptr; j_ha["porcentaje"] = nullptr;
    } else {
      j_ha["valor"]      = ha.valor;
      j_ha["porcentaje"] = ha.valor;
      j_ha["ema"]        = redondear(ha.ema, 2);
      j_ha["desviacion"] = redondear(ha.desviacion, 3);
    }
    j_ha["valido"] = ha.valido;

    // temperatura_ambiente
    JsonObject j_ta = doc.createNestedObject("temperatura_ambiente");
    j_ta["id_asignacion"] = id_asignacion_temperatura_ambiente;
    if (!ta.valido) {
      j_ta["valor"] = nullptr; j_ta["temperatura"] = nullptr;
    } else {
      j_ta["valor"]       = ta.valor;
      j_ta["temperatura"] = ta.valor;
      j_ta["ema"]         = redondear(ta.ema, 2);
      j_ta["desviacion"]  = redondear(ta.desviacion, 3);
    }
    j_ta["valido"] = ta.valido;

    // temperatura_suelo
    JsonObject j_ts = doc.createNestedObject("temperatura_suelo");
    j_ts["id_asignacion"] = id_asignacion_temperatura_suelo;
    if (!ts.valido) {
      j_ts["valor"] = nullptr; j_ts["temperatura"] = nullptr;
    } else {
      j_ts["valor"]       = ts.valor;
      j_ts["temperatura"] = ts.valor;
      j_ts["ema"]         = redondear(ts.ema, 2);
      j_ts["desviacion"]  = redondear(ts.desviacion, 3);
    }
    j_ts["valido"] = ts.valido;

    char buffer[768];
    size_t n = serializeJson(doc, buffer, sizeof(buffer));

    if (mqttClient.publish(topicSensores.c_str(), buffer, false)) {
      Serial.printf("📤 MQTT publicado (%d bytes)\n", (int)n);
    } else {
      Serial.println("❌ Error publicando MQTT");
    }

    ultimaPublicacion = ahora;
    vTaskDelay(50 / portTICK_PERIOD_MS);
  }
}


// ══════════════════════════════════════════════════════════════════
// SETUP
// ══════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(1000);
  cargarConfiguracion();
  Serial.println("\n=== Yaku ESP32-S3 v2.0 – Alta Precisión ===");

  xMutex = xSemaphoreCreateMutex();
  if (!xMutex) { Serial.println("❌ Mutex error"); while (true) delay(1000); }

  if (configuracionCompleta()) {
    conectarWiFi();
    conectarMQTT();
  } else {
    Serial.println("YAKU_WAITING_PROVISIONING");
  }

  dht.begin();
  ds18b20.begin();
  ds18b20.setResolution(12);   // máxima resolución desde el inicio

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // Stack más grande para taskSensores por las operaciones de sort/estadísticas
  xTaskCreatePinnedToCore(taskSensores, "Sensores", 6144, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(taskMQTT,     "MQTT",     8192, NULL, 1, NULL, 0);

  Serial.println("✅ Sistema iniciado");
}

void loop() {
  procesarProvisionamientoSerial();
  vTaskDelay(50 / portTICK_PERIOD_MS);
}
