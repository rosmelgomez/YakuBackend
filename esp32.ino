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

// ==========================
// WIFI / MQTT
// ==========================
const char *ssid = "HGB_2,4GHz";
const char *password = "@Hgb153427986@";

const char *mqtt_host = "85e1c3e7d56d4acbb5070d22345206ec.s1.eu.hivemq.cloud";
const uint16_t mqtt_port = 8883;
const char *mqtt_user = "hivemq.webclient.1778630712813";
const char *mqtt_password = "pVA$d1KU,>R7gM30b@vo";
const char *mqtt_client_id = "ESP32_Yaku_002";

const char *TOPIC_CONTROL_AGUA = "yaku/tanque/datos";

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
const int id_asignacion_proximidad = 6;

WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

bool funcionamientoActivo = false;
bool bombaSolicitada = false;
bool ultimoEstadoBomba = false;
float ultimaDistanciaValida = -1;

// ==========================
// WIFI
// ==========================
void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.print("Conectando a WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

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
  String configTopic = "yaku/dispositivo/" + String(mqtt_client_id) + "/config";

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
      }
    }
  } else if (topicStr == topicComando) {
    String mensajeUP = mensaje;
    mensajeUP.toUpperCase();
    if (funcionamientoActivo) {
      if (mensajeUP == "ON" || mensajeUP == "1" || mensajeUP == "HIGH") {
        bombaSolicitada = true;
        Serial.printf("%s solicito bomba ON\n", modoRiego.c_str());
      } else if (mensajeUP == "OFF" || mensajeUP == "0" || mensajeUP == "LOW") {
        bombaSolicitada = false;
        Serial.printf("%s solicito bomba OFF\n", modoRiego.c_str());
      }
      digitalWrite(RELE_PIN, bombaSolicitada ? HIGH : LOW);
    } else {
      Serial.println("⚠️ Bomba comandada pero el dispositivo está INACTIVO.");
    }
  }
}

void conectarMQTT() {
  espClient.setInsecure();
  mqttClient.setServer(mqtt_host, mqtt_port);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(60);
  mqttClient.setBufferSize(512);

  uint8_t intentos = 0;
  while (!mqttClient.connected() && intentos < 5) {
    Serial.print("Conectando a MQTT...");
    if (mqttClient.connect(mqtt_client_id, mqtt_user, mqtt_password)) {
      Serial.println(" conectado");
      mqttClient.subscribe(topicComando.c_str());

      String configTopic =
          "yaku/dispositivo/" + String(mqtt_client_id) + "/config";
      mqttClient.subscribe(configTopic.c_str());
      Serial.printf("Suscrito a config: %s\n", configTopic.c_str());

      String reqTopic = "yaku/dispositivo/" + String(mqtt_client_id) + "/config/req";
      char reqPayload[64];
      snprintf(reqPayload, sizeof(reqPayload), "{\"id_asignacion\":%d}", id_asignacion_proximidad);
      mqttClient.publish(reqTopic.c_str(), reqPayload);
      Serial.printf("Solicitado config en: %s con payload: %s\n", reqTopic.c_str(), reqPayload);
    } else {
      Serial.print(" fallo, estado=");
      Serial.println(mqttClient.state());
      delay(3000);
      intentos++;
    }
  }
}

void publicarControlAguaMQTT(float distancia_cm, const char* estado_bomba, const char* motivo_cierre = "") {
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

  bool ok = mqttClient.publish(TOPIC_CONTROL_AGUA, payload, false);
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

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RELE_PIN, OUTPUT);
  digitalWrite(RELE_PIN, LOW);
  bombaSolicitada = false;
  ultimoEstadoBomba = false;
  ultimaDistanciaValida = -1;

  conectarWiFi();
  conectarMQTT();

  Serial.println("Sistema listo con MQTT...");
}

// ==========================
// LOOP
// ==========================
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
  }

  if (!mqttClient.connected()) {
    conectarMQTT();
  }

  mqttClient.loop();

  if (!funcionamientoActivo) {
    digitalWrite(RELE_PIN, LOW);
    if (ultimoEstadoBomba) {
      ultimoEstadoBomba = false;
      float dist = (ultimaDistanciaValida > 0) ? ultimaDistanciaValida : medirDistancia();
      publicarControlAguaMQTT(dist > 0 ? dist : 0.0, "OFF", "desactivacion");
    }
    delay(1000);
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
    motivo = "sensor_error";
    Serial.println("BOMBA OFF (sensor sin lectura)");
  } else if (d >= distanciaSinAguaCm) {
    bombaActiva = false;
    motivo = "sin_agua";
    Serial.println("BOMBA OFF (sin agua / seguridad)");
  }

  if (bombaActiva) {
    digitalWrite(RELE_PIN, HIGH);
    Serial.printf("BOMBA ON (Modo: %s)\n", modoRiego.c_str());
  } else {
    digitalWrite(RELE_PIN, LOW);
    Serial.println("BOMBA OFF");
  }

  if (bombaActiva != ultimoEstadoBomba) {
    ultimoEstadoBomba = bombaActiva;

    float distanciaParaEnviar = (d > 0) ? d : ultimaDistanciaValida;

    if (distanciaParaEnviar > 0) {
      publicarControlAguaMQTT(distanciaParaEnviar, bombaActiva ? "ON" : "OFF", bombaActiva ? "" : motivo);
    } else {
      Serial.println("No se publica MQTT: sensor sin lectura valida");
    }
  }

  Serial.println("---------------------");
  delay(500);
}