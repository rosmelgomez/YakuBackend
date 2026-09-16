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
#include <math.h>

constexpr uint8_t PIN_VALVULA = 25, PIN_FLUJO = 27;
constexpr uint8_t PIN_SDA = 13, PIN_SCL = 14;
// Cambiar ambos niveles si el modulo de rele es activo en LOW.
constexpr uint8_t RELE_ON = HIGH, RELE_OFF = LOW;
// YF-S201: f(Hz)=7.5*Q(L/min), equivalente a 450 pulsos/L nominales.
// Calibracion volumetrica: K=sum(pulsos)/sum(litros reales).
// Referencias y procedimiento: docs/calibracion-yf-s201.md.
constexpr float PULSOS_POR_LITRO = 450.0f;
float pulsosPorLitro = PULSOS_POR_LITRO;
float factorRiego = PULSOS_POR_LITRO; // Inmutable para cada ciclo y su cierre MQTT.
constexpr uint32_t DEBOUNCE_US = 300; // Maximo ~3333 pulsos/s.
constexpr uint32_t MAX_RIEGO_SEG = 1800;
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
bool conexionPerdidaReportada = false;
bool pendiente = false, lcdDisponible = false, serialDesbordado = false;
uint32_t inicioMs = 0, duracionMs = 0, ejecutadoMs = 0;
uint32_t pulsosCiclo = 0, pulsosAnterior = 0;
uint32_t pulsosMedidos = 0;
uint32_t ultimoReporteMs = 0, ultimoIntentoMs = 0;
float litrosRiego = 0, litrosTotal = 0, caudal = 0; // Caudal siempre en L/s.

float calcularLitros(uint32_t cantidad, float factor) {
  return cantidad / factor;
}

float calcularCaudalLps(uint32_t cantidad, uint32_t intervaloMs, float factor) {
  return intervaloMs ? calcularLitros(cantidad, factor) * 1000.0f / intervaloMs : 0.0f;
}

bool factorValido(float factor) {
  // Limites defensivos de configuracion, no una garantia de precision del sensor.
  return isfinite(factor) && factor >= 100.0f && factor <= 2000.0f;
}

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
  uint32_t ahora = millis();
  if (activo && (ahora - ultimoMonitorMs >= 5000 || !regando)) {
    ultimoMonitorMs = ahora;
    Serial.println("\n── Ciclo de lectura ──────────────────────");
    Serial.printf("  [Flujometro] Pulsos=%lu | Caudal=%.4f L/s | Ciclo=%.3f L\n",
        (unsigned long)pulsosMedidos, caudal, litrosRiego);
    Serial.printf("✅ Riego=%s | Consumido=%.3f L | Acumulado=%.3f L\n",
        regando ? "ON" : "OFF", litrosRiego,
        litrosTotal + (regando ? litrosRiego : 0.0f));
  }
  if (!lcdDisponible) return;
  lcd.setCursor(0, 0);
  lcd.print(regando ? "Riego directo ON " : "Riego directo OFF");
  lcd.setCursor(0, 1);
  // 7 columnas de volumen del evento + espacio + 8 de caudal, siempre juntos.
  // Sobrescribir las 16 columnas evita parpadeo y restos de cifras anteriores.
  char volumen[24], flujo[24];
  float totalAcumulado = litrosTotal + (regando ? litrosRiego : 0.0f);
  int decimales = totalAcumulado < 999.995f ? 2 : (totalAcumulado < 9999.95f ? 1 : 0);
  snprintf(volumen, sizeof(volumen), "%6.*fL", decimales, totalAcumulado);
  snprintf(flujo, sizeof(flujo), "%5.3fL/s", caudal);
  char linea[17];
  snprintf(linea, sizeof(linea), "%s %s",
      strlen(volumen) == 7 ? volumen : "######L",
      strlen(flujo) == 8 ? flujo : "#####L/s");
  lcd.print(linea);
}

void cerrarRiego(const char* motivo) {
  if (regando) Serial.printf("YAKU_VALVE_OFF reason=%s\n", motivo);
  digitalWrite(PIN_VALVULA, RELE_OFF);
  if (!regando && pendiente) return; // Conservar el cierre pendiente de transmitir.
  if (regando) {
    ejecutadoMs = millis() - inicioMs;
    pulsosMedidos = leerPulsos() - pulsosCiclo;
    litrosRiego = calcularLitros(pulsosMedidos, factorRiego);
    litrosTotal += litrosRiego;
    prefs.begin("yaku_directo", false);
    prefs.putFloat("litros_tot", litrosTotal);
    prefs.end();
    cierrePendiente = true;
    Serial.printf("✅ Riego finalizado: %.3f L | Pulsos=%lu | K=%.4f pulsos/L | Motivo: %s\n",
        litrosRiego, (unsigned long)pulsosMedidos, factorRiego, motivo);
  }
  regando = false;
  conexionPerdidaReportada = false;
  caudal = 0;
  motivoCierre = motivo;
  pendiente = true;

  // Por defecto el sensor de flujo deja de capturar datos al detenerse la valvula
  activo = false;

  mostrarEstado();
}

bool publicarEstado() {
  if (!mqtt.connected() || idAsignacion <= 0) return false;
  StaticJsonDocument<768> doc;
  doc["id_asignacion"] = idAsignacion;
  doc["tipo_fuente"] = "manguera";
  doc["metodo_medicion"] = "flujometro";
  doc["pulsos_riego"] = pulsosMedidos;
  doc["pulsos_por_litro"] = factorRiego;
  doc["distancia_cm"] = -1; // No aplica; nunca simular nivel de tanque.
  // Compatibilidad: estado_bomba es el estado LOGICO del riego en el backend.
  doc["estado_bomba"] = regando ? "ON" : "OFF";
  doc["bomba_fisica_encendida"] = false;
  doc["valvula_abierta"] = false; // Campo legado: valvula de RELLENO del tanque.
  doc["valvula_riego_abierta"] = regando;
  doc["litros_riego"] = litrosRiego;
  doc["litros_acumulados"] = litrosTotal + (regando ? litrosRiego : 0.0f);
  doc["caudal_l_s"] = caudal;
  // El backend existente almacena L/min: conversion explicita, nunca cambiar
  // la unidad de un campo legado sin migrar sus consumidores e historicos.
  doc["caudal_l_min"] = caudal * 60.0f;
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
  litrosTotal = prefs.getFloat("litros_tot", 0.0f);
  float guardado = prefs.getFloat("flujo_k", PULSOS_POR_LITRO);
  pulsosPorLitro = factorValido(guardado) ? guardado : PULSOS_POR_LITRO;
  factorRiego = pulsosPorLitro;
  prefs.end();
  Serial.printf("YAKU_FLOW_CALIBRATION K=%.4f pulsos/L | Unidad=L/s\n", pulsosPorLitro);
}

// Comando local por USB. No abre la valvula ni altera credenciales o historicos.
bool procesarCalibracion(const String& payload) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload) || doc["accion"] != "CALIBRAR_FLUJO") return false;
  if (regando || cierrePendiente) {
    Serial.println("YAKU_CALIBRATION_ERROR detener_riego_y_enviar_cierre_primero");
    return true;
  }
  double cantidad = doc["pulsos"].as<double>();
  double volumen = doc["litros_reales"].as<double>();
  float factor = volumen > 0 ? cantidad / volumen : 0;
  if (!doc["pulsos"].is<uint32_t>() || cantidad <= 0 ||
      !doc["litros_reales"].is<double>() || !isfinite(volumen) || !factorValido(factor)) {
    Serial.println("YAKU_CALIBRATION_ERROR pulsos_o_litros_invalidos");
    return true;
  }
  if (!prefs.begin("yaku_directo", false)) {
    Serial.println("YAKU_CALIBRATION_ERROR almacenamiento");
    return true;
  }
  bool ok = prefs.putFloat("flujo_k", factor) == sizeof(float) &&
      prefs.getFloat("flujo_k", 0) == factor;
  prefs.end();
  if (ok) {
    pulsosPorLitro = factor;
    Serial.printf("YAKU_CALIBRATION_OK K=%.4f pulsos/L; aplica_al_proximo_riego\n", factor);
  } else Serial.println("YAKU_CALIBRATION_ERROR almacenamiento");
  return true;
}

bool provisionar(const String& payload) {
  DynamicJsonDocument doc(4096);
  if (deserializeJson(doc, payload)) return false;
  // Validar antes de modificar la configuracion persistida.
  String fuente = doc["tipo_fuente"] | (doc["tanque"]["tipo_fuente"] | "");
  if (!doc["metodo_medicion"].isNull() && doc["metodo_medicion"] != "flujometro") return false;
  if ((fuente != "manguera" && fuente != "conexion_directa") || !doc["wifi"]["ssid"].is<const char*>() ||
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
      if (!serialDesbordado && procesarCalibracion(serialBuffer)) {
        serialBuffer = "";
        continue;
      }
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
    if (doc.containsKey("litros_acumulados")) {
      litrosTotal = doc["litros_acumulados"].as<float>();
      prefs.begin("yaku_directo", false);
      prefs.putFloat("litros_tot", litrosTotal);
      prefs.end();
      mostrarEstado();
    }
        if (doc.containsKey("id_asignacion")) {
      idAsignacion = doc["id_asignacion"].as<int>();
    } else if (doc.containsKey("asignaciones")) {
      JsonObject asigs = doc["asignaciones"].as<JsonObject>();
      for (JsonPair kv : asigs) {
        if (idAsignacion <= 0) idAsignacion = kv.value().as<int>();
      }
    }
    bool fuenteValida = (tipoFuente == "manguera" || tipoFuente == "conexion_directa" || tipoFuente.isEmpty());
    Serial.printf("YAKU_CONFIG_RECEIVED active=%d valid=%d\n", activo, configRecibida && fuenteValida);
    if (!activo || !fuenteValida) {
      cerrarRiego(fuenteValida ? "desactivacion" : "fuente_incompatible");
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
  bool fuenteValida = (tipoFuente == "manguera" || tipoFuente == "conexion_directa" || tipoFuente.isEmpty());
  if (!fuenteValida) {
    Serial.printf("YAKU_COMMAND_REJECTED fuente=%s\n", tipoFuente.c_str());
    cerrarRiego("fuente_incompatible");
    return;
  }
  // Al abrir la valvula para regar, el sensor de flujo se activa automaticamente para capturar datos
  activo = true;

  // Una orden duplicada no reinicia ni prolonga el limite del ciclo activo.
  if (regando) return;
  if (pendiente && !publicarEstado()) return;
  int segundos = doc["duracion_seg"] | 600;
  if (segundos <= 0) segundos = 600;
  // Margen de seguridad: la aplicacion controla el cronometro y envia OFF al terminar.
  duracionMs = (uint32_t)min((int)(segundos + 60), (int)MAX_RIEGO_SEG) * 1000UL;
  inicioMs = ultimoReporteMs = millis();
  ejecutadoMs = 0;
  pulsosCiclo = pulsosAnterior = leerPulsos();
  pulsosMedidos = 0;
  factorRiego = pulsosPorLitro;
  litrosRiego = caudal = 0;
  motivoCierre = "";
  regando = true;
  digitalWrite(PIN_VALVULA, RELE_ON);
  Serial.println("YAKU_VALVE_ON_GPIO25");
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
  Serial.println("\n=== Yaku ESP32 Flujo v1.0.9 – Litros y caudal L/s ===");
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
    pulsosMedidos = actuales - pulsosCiclo;
    litrosRiego = calcularLitros(pulsosMedidos, factorRiego);
    if (ahora - inicioMs >= duracionMs) cerrarRiego("tiempo_maximo");
    if (regando && ahora - ultimoReporteMs >= REPORTE_MS) {
      caudal = calcularCaudalLps(actuales - pulsosAnterior,
          ahora - ultimoReporteMs, factorRiego);
      pulsosAnterior = actuales;
      ultimoReporteMs = ahora;
      mostrarEstado();
      // Publicar el progreso en vivo para que el backend refleje el riego activo.
      pendiente = true;
    }
  }
  leerSerial();
  if (!mqtt.connected() || WiFi.status() != WL_CONNECTED) {
    if (regando && !conexionPerdidaReportada) {
      Serial.println("YAKU_CONNECTION_LOST_IRRIGATION_CONTINUES_UNTIL_TIMEOUT");
      conexionPerdidaReportada = true;
    }
    conectar();
  } else {
    mqtt.loop();
    if (!configRecibida) pedirConfiguracion();
    if (activo && !regando && ahora - ultimoReporteMs >= 30000) {
      ultimoReporteMs = ahora;
      pendiente = true;
    }
    if (pendiente) publicarEstado();
  }
  if (activo && !regando && millis() - ultimoMonitorMs >= 10000) mostrarEstado();
  delay(1);
}
