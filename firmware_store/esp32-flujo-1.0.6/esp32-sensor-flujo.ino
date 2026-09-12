/*
 * Yaku: conexion directa (fuente "manguera"), ESP32, MQTT y YF-S201.
 * Para tanque: esp32-sensor-proximidad.ino. No hay ciclos de prueba.
 * Valvula normalmente cerrada GPIO25; flujo GPIO27; LCD SDA13/SCL14.
 * Sin bomba: solo se controla la valvula de riego.
 * Dependencias: PubSubClient, ArduinoJson, LiquidCrystal_I2C, core ESP32.
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

constexpr uint8_t PIN_VALVULA = 25, PIN_FLUJO = 27;
constexpr uint8_t PIN_SDA = 13, PIN_SCL = 14;
// Cambiar ambos niveles si el modulo de rele es activo en LOW.
constexpr uint8_t RELE_ON = HIGH, RELE_OFF = LOW;
constexpr float PULSOS_POR_LITRO = 450.0f; // Calibrar con volumen real.
constexpr uint32_t DEBOUNCE_US = 300; // Maximo ~3333 pulsos/s.
constexpr uint32_t MAX_RIEGO_SEG = 1800;
constexpr uint32_t SIN_FLUJO_MS = 10000;
constexpr uint32_t REPORTE_MS = 1000;

LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClientSecure transporte;
PubSubClient mqtt(transporte);
Preferences prefs;
portMUX_TYPE flujoMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t pulsos = 0, ultimoPulsoUs = 0;
String wifiSsid, wifiPassword, mqttHost, mqttUser, mqttPassword, clientId;
String topicPub = "yaku/tanque/datos", topicSub = "yaku/riego/comando";
String tipoFuente, serialBuffer, motivoCierre;
uint16_t mqttPort = 8883;
int idAsignacion = 0;
bool activo = false, configRecibida = false, regando = false;
bool cierrePendiente = false;
bool pendiente = false, lcdDisponible = false, serialDesbordado = false;
uint32_t inicioMs = 0, duracionMs = 0, ejecutadoMs = 0;
uint32_t pulsosCiclo = 0, pulsosAnterior = 0, pulsosVistos = 0, ultimoFlujoMs = 0;
uint32_t pulsosMedidos = 0;
uint32_t ultimoReporteMs = 0, ultimoIntentoMs = 0;
float litrosRiego = 0, litrosTotal = 0, caudal = 0;

uint32_t leerPulsos() {
  portENTER_CRITICAL(&flujoMux);
  uint32_t valor = pulsos;
  portEXIT_CRITICAL(&flujoMux);
  return valor;
}

void IRAM_ATTR contarPulso() {
  uint32_t ahora = micros();
  portENTER_CRITICAL_ISR(&flujoMux);
  if (ahora - ultimoPulsoUs >= DEBOUNCE_US) {
    ++pulsos;
    ultimoPulsoUs = ahora;
  }
  portEXIT_CRITICAL_ISR(&flujoMux);
}

uint32_t ultimoMonitorMs = 0;

void mostrarEstado() {
  ultimoMonitorMs = millis();
  if (activo) {
    Serial.println("\n── Ciclo de lectura ──────────────────────");
    Serial.printf("  [Flujometro] Pulsos=%lu | Caudal=%.2f L/min | Ciclo=%.3f L\n",
        (unsigned long)pulsosMedidos, caudal, litrosRiego);
    Serial.printf("✅ Riego=%s | Consumido=%.3f L | Acumulado=%.3f L\n",
        regando ? "ON" : "OFF", litrosRiego,
        litrosTotal + (regando ? litrosRiego : 0.0f));
  }
  if (!lcdDisponible) return;
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(regando ? "Riego directo ON" : "Riego directo OFF");
  lcd.setCursor(0, 1);
  lcd.print(litrosRiego, 2);
  lcd.print("L ");
  lcd.print(caudal, 1);
  lcd.print("L/m");
}

void cerrarRiego(const char* motivo) {
  if (regando) Serial.printf("YAKU_VALVE_OFF reason=%s\n", motivo);
  digitalWrite(PIN_VALVULA, RELE_OFF);
  if (!regando && pendiente) return; // Conservar el cierre pendiente de transmitir.
  if (regando) {
    ejecutadoMs = millis() - inicioMs;
    pulsosMedidos = leerPulsos() - pulsosCiclo;
    litrosRiego = pulsosMedidos / PULSOS_POR_LITRO;
    litrosTotal += litrosRiego;
    cierrePendiente = true;
    Serial.printf("✅ Riego finalizado: %.3f L consumidos | Motivo: %s\n", litrosRiego, motivo);
  }
  regando = false;
  caudal = 0;
  motivoCierre = motivo;
  pendiente = true;
  mostrarEstado();
}

bool publicarEstado() {
  if (!mqtt.connected() || idAsignacion <= 0) return false;
  StaticJsonDocument<768> doc;
  doc["id_asignacion"] = idAsignacion;
  doc["tipo_fuente"] = "manguera";
  doc["metodo_medicion"] = "flujometro";
  doc["pulsos_riego"] = pulsosMedidos;
  doc["pulsos_por_litro"] = PULSOS_POR_LITRO;
  doc["distancia_cm"] = -1; // No aplica; nunca simular nivel de tanque.
  // Compatibilidad: estado_bomba es el estado LOGICO del riego en el backend.
  doc["estado_bomba"] = regando ? "ON" : "OFF";
  doc["bomba_fisica_encendida"] = false;
  doc["valvula_abierta"] = false; // Campo legado: valvula de RELLENO del tanque.
  doc["valvula_riego_abierta"] = regando;
  doc["litros_riego"] = litrosRiego;
  doc["litros_acumulados"] = litrosTotal + (regando ? litrosRiego : 0.0f);
  doc["caudal_l_min"] = caudal;
  doc["duracion_objetivo_seg"] = duracionMs / 1000;
  uint32_t transcurrido = regando ? millis() - inicioMs : ejecutadoMs;
  doc["tiempo_ejecutado_seg"] = transcurrido / 1000;
  doc["tiempo_restante_seg"] = regando && duracionMs > transcurrido
      ? (duracionMs - transcurrido + 999) / 1000 : 0;
  if (!motivoCierre.isEmpty()) doc["motivo_cierre"] = motivoCierre;
  char buffer[768];
  size_t n = serializeJson(doc, buffer, sizeof(buffer));
  bool ok = mqtt.publish(topicPub.c_str(), (const uint8_t*)buffer, n, false);
  if (ok) {
    pendiente = false;
    if (activo || cierrePendiente) Serial.printf("📤 MQTT publicado (%u bytes)\n", (unsigned)n);
    if (cierrePendiente) {
      Serial.printf("📤 Cierre MQTT enviado: litros_riego=%.3f L | estado_bomba=OFF\n", litrosRiego);
      cierrePendiente = false;
    }
  }
  return ok;
}

void cargarConfiguracion() {
  prefs.begin("yaku_directo", true);
  wifiSsid = prefs.getString("ssid", "");
  wifiPassword = prefs.getString("wifi_pass", "");
  mqttHost = prefs.getString("host", "");
  mqttPort = prefs.getUShort("port", 8883);
  mqttUser = prefs.getString("user", "");
  mqttPassword = prefs.getString("pass", "");
  clientId = prefs.getString("client", "");
  topicPub = prefs.getString("pub", topicPub);
  topicSub = prefs.getString("sub", topicSub);
  tipoFuente = prefs.getString("fuente", "");
  idAsignacion = prefs.getInt("asig", 0);
  prefs.end();
}

bool provisionar(const String& payload) {
  DynamicJsonDocument doc(4096);
  if (deserializeJson(doc, payload)) return false;
  // Validar antes de modificar la configuracion persistida.
  String fuente = doc["tipo_fuente"] | (doc["tanque"]["tipo_fuente"] | "");
  if (!doc["metodo_medicion"].isNull() && doc["metodo_medicion"] != "flujometro") return false;
  if (fuente != "manguera" || !doc["wifi"]["ssid"].is<const char*>() ||
      !doc["mqtt"]["host"].is<const char*>() || !doc["device_uid"].is<const char*>()) return false;
  String ssid = doc["wifi"]["ssid"].as<String>();
  String host = doc["mqtt"]["host"].as<String>();
  String uid = doc["device_uid"].as<String>();
  int asig = doc["asignaciones"]["CAUDAL"] | (doc["asignaciones"]["NIVEL_AGUA"] | 0);
  int port = doc["mqtt"]["port"] | 8883;
  String sub = doc["mqtt"]["topic_sub"] | "";
  if (ssid.isEmpty() || host.isEmpty() || uid.isEmpty() || asig <= 0 ||
      port <= 0 || port > 65535 || sub.isEmpty() ||
      sub.indexOf('#') >= 0 || sub.indexOf('+') >= 0 ||
      !(doc["mqtt"]["tls"] | true)) return false;
  cerrarRiego("reconfiguracion");
  publicarEstado();
  if (!prefs.begin("yaku_directo", false)) return false;
  prefs.putString("ssid", ssid);
  prefs.putString("wifi_pass", doc["wifi"]["password"] | "");
  prefs.putString("host", host);
  prefs.putUShort("port", port);
  prefs.putString("user", doc["mqtt"]["username"] | "");
  prefs.putString("pass", doc["mqtt"]["password"] | "");
  prefs.putString("client", uid);
  prefs.putString("pub", doc["mqtt"]["topic_pub"] | "yaku/tanque/datos");
  prefs.putString("sub", sub);
  prefs.putString("fuente", fuente);
  prefs.putInt("asig", asig);
  bool guardado = prefs.getString("ssid", "") == ssid &&
      prefs.getString("wifi_pass", "") == String(doc["wifi"]["password"] | "") &&
      prefs.getString("host", "") == host && prefs.getUShort("port", 0) == port &&
      prefs.getString("user", "") == String(doc["mqtt"]["username"] | "") &&
      prefs.getString("pass", "") == String(doc["mqtt"]["password"] | "") &&
      prefs.getString("client", "") == uid && prefs.getString("sub", "") == sub &&
      prefs.getString("fuente", "") == fuente && prefs.getInt("asig", 0) == asig;
  prefs.end();
  return guardado;
}

void leerSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      serialBuffer.trim();
      if (!serialDesbordado && provisionar(serialBuffer)) {
        Serial.println("YAKU_PROVISIONING_OK");
        Serial.flush();
        ESP.restart();
      }
      Serial.println("YAKU_PROVISIONING_ERROR");
      serialBuffer = "";
      serialDesbordado = false;
    } else if (serialBuffer.length() < 4096) {
      serialBuffer += c;
    } else {
      serialDesbordado = true;
    }
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  String configTopic = "yaku/dispositivo/" + clientId + "/config";
  Serial.printf("📥 [%s] Mensaje recibido (%u bytes)\n", topic, length);
  if (String(topic) == configTopic) {
    StaticJsonDocument<2048> doc;
    if (deserializeJson(doc, payload, length)) {
      // Mismo protocolo de habilitacion que esp32-s3.ino.
      String estado;
      for (unsigned int i = 0; i < length; ++i) estado += (char)payload[i];
      estado.trim();
      estado.toUpperCase();
      if (estado == "INACTIVE" || estado == "0" || estado == "OFF" || estado == "CAPTURE_OFF") {
        activo = false;
        cerrarRiego("desactivacion");
        Serial.println("⚙️ Funcionamiento DESACTIVADO por el usuario");
      } else if (estado == "ACTIVE" || estado == "1" || estado == "ON" || estado == "CAPTURE_ON") {
        activo = true;
        // Habilitar no abre la valvula ni reemplaza la validacion de fuente.
        Serial.println("⚙️ Funcionamiento ACTIVADO por el usuario");
      }
      return;
    }
    // Activaciones parciales no pueden autorizar una fuente aun desconocida.
    if (doc.containsKey("tipo_fuente")) {
      tipoFuente = doc["tipo_fuente"].as<String>();
      configRecibida = true;
    }
    if (!doc["metodo_medicion"].isNull() && doc["metodo_medicion"] != "flujometro") {
      tipoFuente = "";
      configRecibida = false;
    }
    if (doc.containsKey("funcionamiento_activo")) {
      activo = doc["funcionamiento_activo"];
      Serial.println(activo ? "⚙️ Funcionamiento ACTIVADO por el usuario" : "⚙️ Funcionamiento DESACTIVADO por el usuario");
    }
    Serial.printf("YAKU_CONFIG_RECEIVED active=%d valid=%d\n", activo, configRecibida && tipoFuente == "manguera");
    if (!activo || tipoFuente != "manguera") {
      cerrarRiego(tipoFuente == "manguera" ? "desactivacion" : "fuente_incompatible");
    }
    return;
  }
  if (String(topic) != topicSub) return;
  StaticJsonDocument<256> doc;
  String accion;
  if (!deserializeJson(doc, payload, length)) {
    accion = doc["accion"] | "";
  } else {
    for (unsigned int i = 0; i < length; ++i) accion += (char)payload[i];
  }
  accion.trim();
  accion.toUpperCase();
  Serial.println("YAKU_COMMAND_RECEIVED");
  if (accion == "OFF" || accion == "0" || accion == "LOW" ||
      accion == "VALVULA_OFF" || accion == "VALVE_OFF") {
    cerrarRiego("usuario"); // OFF se acepta incluso estando inactivo.
    return;
  }
  // VALVULA_ON es una orden de relleno del tanque: no inicia riego directo.
  if (accion != "ON" && accion != "1" && accion != "HIGH") return;
  if (!configRecibida || !activo || tipoFuente != "manguera" || idAsignacion <= 0) {
    Serial.println("YAKU_COMMAND_REJECTED_INACTIVE_OR_CONFIG");
    cerrarRiego("fuente_incompatible");
    return;
  }
  // Una orden duplicada no reinicia ni prolonga el limite del ciclo activo.
  if (regando) return;
  if (pendiente && !publicarEstado()) return;
  int segundos = doc["duracion_seg"] | 600;
  if (segundos <= 0) return;
  duracionMs = (uint32_t)min(segundos, (int)MAX_RIEGO_SEG) * 1000UL;
  inicioMs = ultimoFlujoMs = ultimoReporteMs = millis();
  ejecutadoMs = 0;
  pulsosCiclo = pulsosAnterior = pulsosVistos = leerPulsos();
  pulsosMedidos = 0;
  litrosRiego = caudal = 0;
  motivoCierre = "";
  regando = true;
  digitalWrite(PIN_VALVULA, RELE_ON);
  Serial.println("YAKU_VALVE_ON_GPIO25");
  pendiente = true;
  mostrarEstado();
}

uint32_t ultimoWifiMs = 0, ultimoConfigMs = 0;
bool wifiIniciado = false;

void pedirConfiguracion() {
  if (!mqtt.connected() || (ultimoConfigMs && millis() - ultimoConfigMs < 5000)) return;
  ultimoConfigMs = millis();
  String topic = "yaku/dispositivo/" + clientId + "/config/req";
  StaticJsonDocument<192> doc;
  doc["client_id"] = clientId;
  char buffer[192];
  serializeJson(doc, buffer, sizeof(buffer));
  Serial.println(mqtt.publish(topic.c_str(), buffer) ? "YAKU_CONFIG_REQUESTED" : "YAKU_CONFIG_REQUEST_FAILED");
}

void conectar() {
  if (wifiSsid.isEmpty() || mqttHost.isEmpty() || clientId.isEmpty()) return;
  if (WiFi.status() != WL_CONNECTED) {
    // Dar tiempo a asociacion y DHCP: no reiniciar WiFi.begin cada 5 segundos.
    if (!wifiIniciado || millis() - ultimoWifiMs >= 20000) {
      wifiIniciado = true;
      ultimoWifiMs = millis();
      Serial.println("Conectando WiFi...");
      WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
    }
    return;
  }
  if (millis() - ultimoIntentoMs < 5000) return;
  ultimoIntentoMs = millis();
  Serial.println("Conectando MQTT...");
  if (mqtt.connect(clientId.c_str(), mqttUser.c_str(), mqttPassword.c_str())) {
    Serial.println("✅ MQTT conectado");
    configRecibida = false;
    activo = false;
    String configTopic = "yaku/dispositivo/" + clientId + "/config";
    if (!mqtt.subscribe(topicSub.c_str()) || !mqtt.subscribe(configTopic.c_str())) {
      Serial.println("YAKU_MQTT_SUBSCRIBE_FAILED");
      mqtt.disconnect();
      return;
    }
    Serial.printf("   Suscrito a config: %s\n   Suscrito a comandos: %s\n", configTopic.c_str(), topicSub.c_str());
    ultimoConfigMs = 0;
    pedirConfiguracion();
    pendiente = true;
  } else {
    Serial.printf("YAKU_MQTT_ERROR code=%d\n", mqtt.state());
  }
}

void setup() {
  // Salidas seguras antes de inicializar perifericos o red.
  digitalWrite(PIN_VALVULA, RELE_OFF);
  pinMode(PIN_VALVULA, OUTPUT);
  Serial.setRxBufferSize(4096);
  Serial.begin(115200);
  Serial.println("\n=== Yaku ESP32 Flujo v1.0.6 – Medicion de agua ===");
  pinMode(PIN_FLUJO, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FLUJO), contarPulso, RISING);
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.beginTransmission(0x27);
  lcdDisponible = Wire.endTransmission() == 0;
  if (lcdDisponible) {
    lcd.init();
    lcd.backlight();
  }
  mostrarEstado();
  cargarConfiguracion();
  // Misma politica TLS del firmware de tanque existente (sin validar CA).
  transporte.setInsecure();
  transporte.setTimeout(1000);
  mqtt.setServer(mqttHost.c_str(), mqttPort);
  mqtt.setCallback(callback);
  mqtt.setBufferSize(4096);
  mqtt.setSocketTimeout(5);
  mqtt.setKeepAlive(60);
  transporte.setHandshakeTimeout(8);
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
      Serial.printf("✅ WiFi: %s | Senal: %d dBm\n",
          WiFi.localIP().toString().c_str(), WiFi.RSSI());
    }
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED)
      Serial.printf("YAKU_WIFI_DISCONNECTED reason=%u\n", info.wifi_sta_disconnected.reason);
  });
  WiFi.mode(WIFI_STA);
  Serial.println(wifiSsid.isEmpty() ? "YAKU_WAITING_PROVISIONING" : "YAKU_CONFIG_LOADED");
  Serial.println("✅ Sistema iniciado");
}

void loop() {
  uint32_t ahora = millis();
  if (regando) {
    uint32_t actuales = leerPulsos();
    if (actuales != pulsosVistos) {
      ultimoFlujoMs = ahora;
      pulsosVistos = actuales;
    }
    pulsosMedidos = actuales - pulsosCiclo;
    litrosRiego = pulsosMedidos / PULSOS_POR_LITRO;
    if (ahora - inicioMs >= duracionMs) cerrarRiego("tiempo_maximo");
    else if (ahora - ultimoFlujoMs >= SIN_FLUJO_MS) cerrarRiego("sin_flujo");
    else if (WiFi.status() != WL_CONNECTED || !mqtt.connected()) cerrarRiego("conexion_perdida");
    if (regando && ahora - ultimoReporteMs >= REPORTE_MS) {
      caudal = ((actuales - pulsosAnterior) / PULSOS_POR_LITRO) *
          60000.0f / (ahora - ultimoReporteMs);
      pulsosAnterior = actuales;
      ultimoReporteMs = ahora;
      pendiente = true;
      mostrarEstado();
    }
  }
  leerSerial();
  if (!mqtt.connected() || WiFi.status() != WL_CONNECTED) {
    if (regando) cerrarRiego("conexion_perdida");
    configRecibida = false;
    activo = false;
    conectar();
  } else {
    mqtt.loop();
    if (!configRecibida) pedirConfiguracion();
    if (!regando && ahora - ultimoReporteMs >= 30000) {
      ultimoReporteMs = ahora;
      pendiente = true;
    }
    if (pendiente) publicarEstado();
  }
  if (!regando && millis() - ultimoMonitorMs >= 10000) mostrarEstado();
  delay(1);
}
