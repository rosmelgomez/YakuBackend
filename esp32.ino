/*
  ============================================================
  SISTEMA DE RIEGO - ESP32 + MQTT HiveMQ Cloud
  Publica la distancia del tanque y escucha comandos ON/OFF
  ============================================================
*/

#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <Preferences.h>

// Prototipos de funciones
void publicarControlAguaMQTT(float distancia_cm, const char* estado_bomba, const char* motivo_cierre = "");
float medirDistancia();

// ==========================
// WIFI / MQTT
// ==========================
String wifiSsid = "";
String wifiPassword = "";
String mqttHost = "85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud";
uint16_t mqttPort = 8883;
String mqttUser = "";
String mqttPassword = "";
String mqttClientId = "YAKU-ESP32-UNPROVISIONED";

String topicControlAgua = "yaku/tanque/datos";

// ==========================
// PINES
// ==========================
#define TRIG_PIN 26
#define ECHO_PIN 27
#define RELE_PIN 33

// ==========================
// CONFIGURACION DINAMICA
// ==========================
float alturaTotalCm = 50.0;
float distanciaSinAguaCm = 45.0;
String modoRiego = "manual";
String topicComando = "yaku/riego/comando";

// ==========================
// ESTADO
// ==========================
int id_asignacion_proximidad = 0;

WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

bool funcionamientoActivo = false;
bool bombaSolicitada = false;
bool ultimoEstadoBomba = false;
unsigned long inicioReleMs = 0;
uint32_t duracionReleSeg = 600;
const uint32_t DURACION_RELE_MIN_SEG = 60;
const uint32_t DURACION_RELE_MAX_SEG = 1800;
float ultimaDistanciaValida = -1;
unsigned long ultimoEnvioNivel = 0;
const unsigned long INTERVALO_ENVIO_NIVEL = 30000; // 30 segundos
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
  preferences.putString("topic_pub", topicControlAgua);
  preferences.putString("topic_sub", topicComando);
  preferences.putInt("asig_nivel", id_asignacion_proximidad);
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
  topicControlAgua = preferences.getString("topic_pub", topicControlAgua);
  topicComando = preferences.getString("topic_sub", topicComando);
  id_asignacion_proximidad = preferences.getInt("asig_nivel", 0);
  preferences.end();
}

bool configuracionCompleta() {
  return wifiSsid.length() > 0 && wifiPassword.length() > 0 &&
         mqttHost.length() > 0 && mqttPort > 0 &&
         mqttUser.length() > 0 && mqttPassword.length() > 0 &&
         mqttClientId.length() > 0 && id_asignacion_proximidad > 0;
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
    if (mqtt.containsKey("topic_pub") && !mqtt["topic_pub"].isNull()) topicControlAgua = mqtt["topic_pub"].as<String>();
    if (mqtt.containsKey("topic_sub") && !mqtt["topic_sub"].isNull()) topicComando = mqtt["topic_sub"].as<String>();
  }
  id_asignacion_proximidad = asig["NIVEL_AGUA"] | 0;
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

// ==========================
// WIFI
// ==========================
void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.print("Conectando a WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());

  uint8_t intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(500);
    Serial.print(".");
    intentos++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("WiFi conectado: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("WiFi sin conexion");
  }
}

// ==========================
// MQTT
// ==========================
void mqttCallback(char *topic, byte *payload, unsigned int length) {
  String mensaje;
  for (unsigned int i = 0; i < length; i++) {
    mensaje += (char)payload[i];
  }
  mensaje.trim();

  Serial.print("MQTT recibido [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(mensaje);

  String topicStr = String(topic);
  String configTopic = "yaku/dispositivo/" + mqttClientId + "/config";

  if (topicStr == configTopic) {
    // Intentar deserializar JSON
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, mensaje);
    if (!error) {
      if (doc.containsKey("funcionamiento_activo")) {
        funcionamientoActivo = doc["funcionamiento_activo"];
        Serial.printf("⚙️ Funcionamiento: %s\n", funcionamientoActivo ? "ACTIVO" : "DESACTIVADO");
        if (!funcionamientoActivo) {
          digitalWrite(RELE_PIN, LOW);
          Serial.println("🔒 Bomba APAGADA (por desactivacion)");
        } else {
          Serial.println("Dispositivo activo; sensor de nivel en espera de una orden de riego");
        }
      }
      if (doc.containsKey("altura_total_cm")) {
        alturaTotalCm = doc["altura_total_cm"];
        Serial.printf("⚙️ Altura total cm: %.2f\n", alturaTotalCm);
      }
      if (doc.containsKey("distancia_sin_agua_cm")) {
        distanciaSinAguaCm = doc["distancia_sin_agua_cm"];
        Serial.printf("⚙️ Distancia sin agua cm: %.2f\n", distanciaSinAguaCm);
      }
      if (doc.containsKey("modo")) {
        modoRiego = doc["modo"].as<String>();
        Serial.printf("⚙️ Modo de riego: %s\n", modoRiego.c_str());
      }
      if (doc.containsKey("topic_sub")) {
        String nuevoTopic = doc["topic_sub"].as<String>();
        if (nuevoTopic != topicComando) {
          Serial.printf("⚙️ Cambiando suscripcion de %s a %s\n", topicComando.c_str(), nuevoTopic.c_str());
          mqttClient.unsubscribe(topicComando.c_str());
          topicComando = nuevoTopic;
          mqttClient.subscribe(topicComando.c_str());
        }
      }
      JsonObject asig = doc["asignaciones"];
      if (!asig.isNull() && asig.containsKey("NIVEL_AGUA")) {
        id_asignacion_proximidad = asig["NIVEL_AGUA"];
        guardarConfiguracion();
      }
    } else {
      // Fallback para mensajes planos antiguos
      String mensajeUP = mensaje;
      mensajeUP.toUpperCase();
      if (mensajeUP == "INACTIVE" || mensajeUP == "0" || mensajeUP == "OFF" ||
          mensajeUP == "CAPTURE_OFF") {
        funcionamientoActivo = false;
        Serial.println("⚙️ Funcionamiento DESACTIVADO por el usuario");
        digitalWrite(RELE_PIN, LOW);
        Serial.println("🔒 Bomba APAGADA (por desactivacion)");
      } else if (mensajeUP == "ACTIVE" || mensajeUP == "1" || mensajeUP == "ON" ||
                 mensajeUP == "CAPTURE_ON") {
        funcionamientoActivo = true;
        Serial.println("⚙️ Funcionamiento ACTIVADO por el usuario");
        Serial.println("Sensor de nivel en espera de una orden de riego");
      }
    }
  } else if (topicStr == topicComando) {
    String accion = mensaje;
    uint32_t duracionSolicitada = duracionReleSeg;
    StaticJsonDocument<128> commandDoc;
    DeserializationError commandError = deserializeJson(commandDoc, mensaje);
    if (!commandError && commandDoc.containsKey("accion")) {
      accion = commandDoc["accion"].as<String>();
      duracionSolicitada = commandDoc["duracion_seg"] | duracionReleSeg;
    }
    accion.toUpperCase();
    if (funcionamientoActivo) {
      if (accion == "ON" || accion == "1" || accion == "HIGH") {
        duracionSolicitada = constrain(
          duracionSolicitada,
          DURACION_RELE_MIN_SEG,
          DURACION_RELE_MAX_SEG
        );
        if (!bombaSolicitada) {
          inicioReleMs = 0;
        }
        duracionReleSeg = duracionSolicitada;
        bombaSolicitada = true;
        Serial.printf(
          "%s solicito bomba ON por un maximo de %lu segundos; validando nivel\n",
          modoRiego.c_str(),
          (unsigned long)duracionReleSeg
        );
      } else if (accion == "OFF" || accion == "0" || accion == "LOW") {
        bombaSolicitada = false;
        inicioReleMs = 0;
        digitalWrite(RELE_PIN, LOW);
        Serial.printf("%s solicito bomba OFF\n", modoRiego.c_str());
      }
    } else {
      Serial.println("⚠️ Bomba comandada pero el dispositivo está INACTIVO.");
    }
  }
}

void conectarMQTT() {
  espClient.setInsecure();
  mqttClient.setServer(mqttHost.c_str(), mqttPort);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(60);
  mqttClient.setBufferSize(512);

  uint8_t intentos = 0;
  while (!mqttClient.connected() && intentos < 5) {
    Serial.print("Conectando a MQTT...");
    if (mqttClient.connect(mqttClientId.c_str(), mqttUser.c_str(), mqttPassword.c_str())) {
      Serial.println(" conectado");
      mqttClient.subscribe(topicComando.c_str());

      String configTopic =
          "yaku/dispositivo/" + mqttClientId + "/config";
      mqttClient.subscribe(configTopic.c_str());
      Serial.printf("Suscrito a config: %s\n", configTopic.c_str());

      String reqTopic = "yaku/dispositivo/" + mqttClientId + "/config/req";
      String reqPayload = "{\"client_id\":\"" + mqttClientId + "\"}";
      mqttClient.publish(reqTopic.c_str(), reqPayload.c_str());
      Serial.printf("Solicitado config en: %s\n", reqTopic.c_str());
    } else {
      Serial.print(" fallo, estado=");
      Serial.println(mqttClient.state());
      delay(3000);
      intentos++;
    }
  }
}

void publicarControlAguaMQTT(float distancia_cm, const char* estado_bomba, const char* motivo_cierre) {
  char payload[192];
  if (strcmp(estado_bomba, "OFF") == 0) {
    snprintf(
      payload,
      sizeof(payload),
      "{\"id_asignacion\":%d,\"distancia_cm\":%.2f,\"estado_bomba\":\"%s\",\"motivo_cierre\":\"%s\"}",
      id_asignacion_proximidad,
      distancia_cm,
      estado_bomba,
      motivo_cierre
    );
  } else {
    snprintf(
      payload,
      sizeof(payload),
      "{\"id_asignacion\":%d,\"distancia_cm\":%.2f,\"estado_bomba\":\"%s\"}",
      id_asignacion_proximidad,
      distancia_cm,
      estado_bomba
    );
  }

  bool ok = mqttClient.publish(topicControlAgua.c_str(), payload, false);
  if (ok) {
    Serial.print("MQTT publicado: ");
    Serial.println(payload);
  } else {
    Serial.println("Error publicando en MQTT");
  }
}

// ==========================
// SENSOR
// ==========================
float medirDistancia() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duracion = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duracion == 0) {
    return -1;
  }

  return duracion * 0.034 / 2;
}

// ==========================
// SETUP
// ==========================
void setup() {
  Serial.begin(115200);
  cargarConfiguracion();

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RELE_PIN, OUTPUT);
  digitalWrite(RELE_PIN, LOW);
  bombaSolicitada = false;
  ultimoEstadoBomba = false;
  ultimaDistanciaValida = -1;

  if (configuracionCompleta()) {
    conectarWiFi();
    conectarMQTT();
  } else {
    Serial.println("YAKU_WAITING_PROVISIONING");
  }

  Serial.println("Sistema listo con MQTT...");
}

// ==========================
// LOOP
// ==========================
void loop() {
  procesarProvisionamientoSerial();
  if (!configuracionCompleta()) {
    delay(100);
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
  }

  if (!mqttClient.connected()) {
    conectarMQTT();
  }

  mqttClient.loop();

  if (!funcionamientoActivo) {
    bombaSolicitada = false;
    inicioReleMs = 0;
    digitalWrite(RELE_PIN, LOW);
    if (ultimoEstadoBomba) {
      ultimoEstadoBomba = false;
      publicarControlAguaMQTT(
        ultimaDistanciaValida > 0 ? ultimaDistanciaValida : 0.0,
        "OFF",
        "desactivacion"
      );
    }
    delay(1000);
    return;
  }

  // El sensor ultrasonico solo captura mientras existe una solicitud de riego.
  if (!bombaSolicitada) {
    inicioReleMs = 0;
    digitalWrite(RELE_PIN, LOW);
    if (ultimoEstadoBomba) {
      ultimoEstadoBomba = false;
      ultimoEnvioNivel = millis();
      publicarControlAguaMQTT(
        ultimaDistanciaValida > 0 ? ultimaDistanciaValida : 0.0,
        "OFF",
        "comando"
      );
    }
    delay(100);
    return;
  }

  float d = medirDistancia();

  Serial.print("Distancia: ");
  Serial.print(d);
  Serial.println(" cm");

  if (d > 0) {
    ultimaDistanciaValida = d;
  }

  bool bombaActiva = bombaSolicitada;
  const char* motivo = "sistema";

  if (d < 0) {
    bombaActiva = false;
    bombaSolicitada = false;
    motivo = "sensor_error";
    Serial.println("BOMBA OFF (sensor sin lectura)");
  } else if (d >= distanciaSinAguaCm) {
    bombaActiva = false;
    bombaSolicitada = false;
    motivo = "sin_agua";
    Serial.println("BOMBA OFF (sin agua / seguridad)");
  }

  if (bombaActiva) {
    if (inicioReleMs == 0) {
      inicioReleMs = millis();
    } else if (millis() - inicioReleMs >= duracionReleSeg * 1000UL) {
      bombaActiva = false;
      bombaSolicitada = false;
      motivo = "tiempo_maximo";
      Serial.println("BOMBA OFF (tiempo maximo del rele alcanzado)");
    }
  }

  if (bombaActiva) {
    digitalWrite(RELE_PIN, HIGH);
    Serial.printf("BOMBA ON (Modo: %s)\n", modoRiego.c_str());
  } else {
    digitalWrite(RELE_PIN, LOW);
    inicioReleMs = 0;
    Serial.println("BOMBA OFF");
  }

  bool rechazoSeguridad = !bombaActiva && (strcmp(motivo, "sistema") != 0);
  if (rechazoSeguridad || bombaActiva != ultimoEstadoBomba ||
      (bombaActiva && millis() - ultimoEnvioNivel >= INTERVALO_ENVIO_NIVEL)) {
    ultimoEnvioNivel = millis();
    ultimoEstadoBomba = bombaActiva;

    float distanciaParaEnviar = (d > 0) ? d : ultimaDistanciaValida;

    if (distanciaParaEnviar > 0 || rechazoSeguridad) {
      publicarControlAguaMQTT(
        distanciaParaEnviar > 0 ? distanciaParaEnviar : 0.0,
        bombaActiva ? "ON" : "OFF",
        bombaActiva ? "" : motivo
      );
    } else {
      Serial.println("No se publica MQTT: sensor sin lectura valida");
    }
  }

  Serial.println("---------------------");
  delay(500);
}
