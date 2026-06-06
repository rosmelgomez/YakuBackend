
/*
  ============================================================
  SISTEMA DE RIEGO - ESP32 + MQTT HiveMQ Cloud
  Publica la distancia del tanque y escucha comandos ON/OFF
  ============================================================
*/

#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>


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
const char *TOPIC_COMANDO = "yaku/riego/comando";

// ==========================
// PINES
// ==========================
#define TRIG_PIN 26
#define ECHO_PIN 27
#define RELE_PIN 33

// ==========================
// UMBRALES
// ==========================
const float ALTURA_REFERENCIA_CM = 30.0;
const float DISTANCIA_SIN_AGUA_CM = 20.0;

// ==========================
// ESTADO
// ==========================
const int id_sensor_proximidad = 5;

WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

bool funcionamientoActivo = false;
bool bombaSolicitadaPorML = false;
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
  mensaje.toUpperCase();

  Serial.print("MQTT recibido [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(mensaje);

  String topicStr = String(topic);
  String configTopic = "yaku/dispositivo/" + String(mqtt_client_id) + "/config";

  if (topicStr == configTopic) {
    if (mensaje == "INACTIVE" || mensaje == "0" || mensaje == "OFF" ||
        mensaje == "CAPTURE_OFF") {
      funcionamientoActivo = false;
      Serial.println("⚙️ Funcionamiento DESACTIVADO por el usuario");
      digitalWrite(RELE_PIN, LOW);
      Serial.println("🔒 Bomba APAGADA (por desactivacion)");
    } else if (mensaje == "ACTIVE" || mensaje == "1" || mensaje == "ON" ||
               mensaje == "CAPTURE_ON") {
      funcionamientoActivo = true;
      Serial.println("⚙️ Funcionamiento ACTIVADO por el usuario");
    }
  } else if (topicStr == TOPIC_COMANDO) {
    if (funcionamientoActivo) {
      if (mensaje == "ON" || mensaje == "1" || mensaje == "HIGH") {
        bombaSolicitadaPorML = true;
        Serial.println("ML solicito bomba ON");
      } else if (mensaje == "OFF" || mensaje == "0" || mensaje == "LOW") {
        bombaSolicitadaPorML = false;
        Serial.println("ML solicito bomba OFF");
      }
      digitalWrite(RELE_PIN, bombaSolicitadaPorML ? HIGH : LOW);
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
      mqttClient.subscribe(TOPIC_COMANDO);

      String configTopic =
          "yaku/dispositivo/" + String(mqtt_client_id) + "/config";
      mqttClient.subscribe(configTopic.c_str());
      Serial.printf("Suscrito a config: %s\n", configTopic.c_str());
    } else {
      Serial.print(" fallo, estado=");
      Serial.println(mqttClient.state());
      delay(3000);
      intentos++;
    }
  }
}

void publicarControlAguaMQTT(float distancia_cm, const char *estado_bomba) {
  float nivel_agua_cm = ALTURA_REFERENCIA_CM - distancia_cm;
  if (nivel_agua_cm < 0) {
    nivel_agua_cm = 0;
  }

  float porcentaje_nivel = (nivel_agua_cm / ALTURA_REFERENCIA_CM) * 100.0;
  if (porcentaje_nivel < 0)
    porcentaje_nivel = 0;
  if (porcentaje_nivel > 100)
    porcentaje_nivel = 100;

  char payload[256];
  snprintf(payload, sizeof(payload),
           "{\"sensor\":\"HC-SR04\",\"id_sensor\":%d,\"distancia_cm\":%.2f,"
           "\"altura_referencia_cm\":%.2f,\"nivel_agua_cm\":%.2f,\"porcentaje_"
           "nivel\":%.2f,\"estado_bomba\":\"%s\"}",
           id_sensor_proximidad, distancia_cm, ALTURA_REFERENCIA_CM,
           nivel_agua_cm, porcentaje_nivel, estado_bomba);

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
  bombaSolicitadaPorML = false;
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

  bool bombaActiva = bombaSolicitadaPorML;

  if (d < 0) {
    bombaActiva = false;
    Serial.println("BOMBA OFF (sensor sin lectura)");
  } else if (d >= DISTANCIA_SIN_AGUA_CM) {
    bombaActiva = false;
    Serial.println("BOMBA OFF (sin agua / seguridad)");
  }

  if (bombaActiva) {
    digitalWrite(RELE_PIN, HIGH);
    Serial.println("BOMBA ON (por ML)");
  } else {
    digitalWrite(RELE_PIN, LOW);
    Serial.println("BOMBA OFF");
  }

  if (bombaActiva != ultimoEstadoBomba) {
    ultimoEstadoBomba = bombaActiva;

    float distanciaParaEnviar = (d > 0) ? d : ultimaDistanciaValida;

    if (distanciaParaEnviar > 0) {
      publicarControlAguaMQTT(distanciaParaEnviar, bombaActiva ? "ON" : "OFF");
    } else {
      Serial.println("No se publica MQTT: sensor sin lectura valida");
    }
  }

  Serial.println("---------------------");
  delay(500);
}