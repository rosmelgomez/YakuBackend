#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ========================================
// PINES
// ========================================

#define PIN_VALVULA 25
#define PIN_FLUJO   27

#define PIN_SDA     13
#define PIN_SCL     14


// ========================================
// LCD
// ========================================

// Dirección habitual del módulo I2C
LiquidCrystal_I2C lcd(0x27, 16, 2);


// ========================================
// CONFIGURACIÓN DEL YF-S201
// ========================================

// Valor nominal típico del YF-S201
// Lo podemos calibrar posteriormente.
const float PULSOS_POR_LITRO = 450.0;


// ========================================
// VARIABLES DEL SENSOR
// ========================================

volatile unsigned long pulsos = 0;

unsigned long pulsosRiego = 0;

float litrosRiego = 0.0;
float litrosAcumulados = 0.0;
float caudal = 0.0;


// ========================================
// CONFIGURACIÓN DEL RIEGO
// ========================================

// Tiempo de espera entre el cierre y el siguiente riego
const unsigned long INTERVALO_RIEGO = 10000;

// Tiempo que permanece abierta la válvula
const unsigned long DURACION_RIEGO = 5000;


// ========================================
// INTERRUPCIÓN DEL YF-S201
// ========================================

void IRAM_ATTR contarPulso() {
  pulsos++;
}


// ========================================
// SETUP
// ========================================

void setup() {

  Serial.begin(115200);

  // ------------------------------------
  // VÁLVULA
  // ------------------------------------

  pinMode(PIN_VALVULA, OUTPUT);

  // Válvula inicialmente cerrada
  digitalWrite(PIN_VALVULA, LOW);


  // ------------------------------------
  // YF-S201
  // ------------------------------------

  pinMode(PIN_FLUJO, INPUT);

  attachInterrupt(
    digitalPinToInterrupt(PIN_FLUJO),
    contarPulso,
    RISING
  );


  // ------------------------------------
  // LCD
  // ------------------------------------

  Wire.begin(PIN_SDA, PIN_SCL);

  lcd.init();

  lcd.backlight();
  // Activa la retroiluminación del LCD.

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Sistema riego");

  lcd.setCursor(0, 1);
  lcd.print("Iniciando...");

  delay(2000);

  lcd.clear();


  // ------------------------------------
  // SERIAL
  // ------------------------------------

  Serial.println();
  Serial.println("================================");
  Serial.println("       SISTEMA DE RIEGO");
  Serial.println("================================");

  Serial.println("LCD SDA      -> GPIO 13");
  Serial.println("LCD SCL      -> GPIO 14");
  Serial.println("YF-S201      -> GPIO 27");
  Serial.println("Valvula      -> GPIO 25");

  Serial.println();
  Serial.println("Intervalo riego : 10 segundos");
  Serial.println("Duracion riego  : 5 segundos");
  Serial.println();

  Serial.println("Sistema iniciado.");
  Serial.println();


  // Esperamos 10 segundos antes del primer riego
  delay(INTERVALO_RIEGO);
}


// ========================================
// LOOP
// ========================================

void loop() {

  // ======================================
  // PREPARAR NUEVO RIEGO
  // ======================================

  Serial.println();
  Serial.println("================================");
  Serial.println("       NUEVO CICLO DE RIEGO");
  Serial.println("================================");


  // Reiniciamos contador de pulsos
  noInterrupts();
  pulsos = 0;
  interrupts();


  // Reiniciamos datos del riego actual
  litrosRiego = 0.0;
  caudal = 0.0;


  // ======================================
  // ABRIR VÁLVULA
  // ======================================

  Serial.println("Abriendo valvula...");

  digitalWrite(PIN_VALVULA, HIGH);


  // Mostrar en LCD
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Riego activo");

  lcd.setCursor(0, 1);
  lcd.print("Midiendo agua");


  // ======================================
  // MANTENER VÁLVULA ABIERTA
  // ======================================

  unsigned long inicioRiego = millis();
  unsigned long ultimoReporte = inicioRiego;

  while (millis() - inicioRiego < DURACION_RIEGO) {

    // Mostrar información cada cierto tiempo
    const unsigned long ahora = millis();

    if (ahora - ultimoReporte >= 1000) {

      ultimoReporte = ahora;

      noInterrupts();
      unsigned long pulsosActuales = pulsos;
      interrupts();


      // Caudal aproximado durante el riego
      caudal =
        (pulsosActuales / PULSOS_POR_LITRO)
        * 60.0
        /
        ((ahora - inicioRiego) / 1000.0);


      Serial.print("Pulsos: ");
      Serial.print(pulsosActuales);

      Serial.print(" | Caudal aprox: ");
      Serial.print(caudal, 2);

      Serial.println(" L/min");
    }

    delay(10);
  }


  // ======================================
  // CERRAR VÁLVULA
  // ======================================

  digitalWrite(PIN_VALVULA, LOW);
  const unsigned long tiempoRiegoMs = millis() - inicioRiego;

  Serial.println();
  Serial.println("Valvula cerrada.");


  // ======================================
  // OBTENER PULSOS DEL RIEGO
  // ======================================

  noInterrupts();
  pulsosRiego = pulsos;
  interrupts();


  // ======================================
  // CALCULAR LITROS
  // ======================================

  litrosRiego =
    pulsosRiego / PULSOS_POR_LITRO;


  litrosAcumulados += litrosRiego;


  // Caudal promedio durante el tiempo real del riego (ms a minutos)
  caudal =
    litrosRiego
    /
    (tiempoRiegoMs / 60000.0);


  // ======================================
  // MOSTRAR RESULTADOS EN SERIAL
  // ======================================

  Serial.println();
  Serial.println("---------- RESULTADO ----------");

  Serial.print("Pulsos detectados: ");
  Serial.println(pulsosRiego);

  Serial.print("Litros del riego: ");
  Serial.print(litrosRiego, 3);
  Serial.println(" L");

  Serial.print("Caudal promedio: ");
  Serial.print(caudal, 2);
  Serial.println(" L/min");

  Serial.print("Litros acumulados: ");
  Serial.print(litrosAcumulados, 3);
  Serial.println(" L");

  Serial.println("--------------------------------");


  // ======================================
  // MOSTRAR RESULTADO EN LCD
  // ======================================

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Riego:");
  lcd.print(litrosRiego, 2);
  lcd.print(" L");

  lcd.setCursor(0, 1);
  lcd.print("Total:");
  lcd.print(litrosAcumulados, 2);
  lcd.print(" L");


  // ======================================
  // ESPERAR 10 SEGUNDOS
  // ======================================

  Serial.println();
  Serial.println("Esperando 10 segundos...");
  Serial.println();

  delay(INTERVALO_RIEGO);
}