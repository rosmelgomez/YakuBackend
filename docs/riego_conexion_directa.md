# Firmware de conexion directa

`esp32-sensor-flujo.ino` (antes `riego_mqtt_v2.ino`) controla una fuente `manguera` (tuberia con suministro
presurizado), mediante una valvula normalmente cerrada y un YF-S201.
El firmware de tanque es `esp32-sensor-proximidad.ino`.

| Elemento | GPIO |
| --- | --- |
| Rele de valvula de riego | 25 |
| Pulsos YF-S201 | 27 |
| LCD SDA / SCL | 13 / 14 |

Los reles se consideran activos en HIGH. Ajustar `RELE_ON` y `RELE_OFF`
si el modulo usa logica inversa. Las entradas del ESP32 deben recibir
senales compatibles con 3.3 V. El LCD utiliza 0x27. GPIO33 no se configura
ni se escribe: esta instalacion no utiliza bomba.
El factor inicial del caudalimetro es 450 pulsos/litro; calibrarlo con un
volumen medido. `litros_acumulados` se reinicia al reiniciar el equipo.

## Instalacion

1. En administrador, registrar **ESP32 (Actuador con flujometro)** y asignarlo
   a un cultivo con fuente **conexion_directa**. Para tanque se registra
   **ESP32 (Actuador con proximidad)**.
   Agregar el componente **Flujometro YF-S201** al dispositivo con metrica
   **CAUDAL** y GPIO 27; agregar la valvula como actuador en GPIO 25.
2. Compilar este sketch para ESP32 con PubSubClient, ArduinoJson y
   LiquidCrystal_I2C. En Arduino IDE, guardarlo en una carpeta llamada
   `esp32-sensor-flujo`.
3. Flashear y enviar la configuracion desde la pantalla de firmware.
   El backend y el frontend incluyen `tipo_fuente` y `metodo_medicion`.
   La configuracion WiFi/MQTT se conserva en NVS (`yaku_directo`).
4. Activar el dispositivo. En cada conexion se solicita la configuracion
   MQTT; solo se permite regar al confirmar `tipo_fuente: "manguera"`
   y `funcionamiento_activo: true`.

El aprovisionamiento asigna un topic de comando por dispositivo cuando
se utilizaba el topic compartido predeterminado. No publicar ordenes ON
retenidas. La conexion TLS conserva la politica del firmware existente:
`setInsecure()` cifra el transporte pero no valida el certificado del broker.

## Operacion

`{"accion":"ON","duracion_seg":120}` inicia el riego; `{"accion":"OFF"}`
lo detiene. Tambien se admiten los comandos planos ON/OFF existentes.
El limite local es 1800 segundos y un ON repetido durante el ciclo no
prolonga ese limite. No hay ciclos automaticos de prueba.

La valvula se cierra si pasan 10 segundos sin pulsos, termina el tiempo,
se desactiva el equipo o se detecta perdida de WiFi/MQTT. Las reconexiones
se intentan con las salidas apagadas. No se reanuda automaticamente tras
una desconexion o reinicio. `VALVULA_ON` es una orden de relleno de tanque
y no inicia riego directo.

La telemetria publica caudal y litros cada segundo durante el riego, el
cierre final y un estado cada 30 segundos en reposo. Para conservar la
compatibilidad del backend, `estado_bomba` representa el **riego activo**;
`bomba_fisica_encendida` permanece falso y `valvula_riego_abierta` informa
la salida real. `valvula_abierta` es el campo de relleno del tanque y queda
falso. La distancia -1 del firmware se almacena como NULL y el backend no
calcula porcentaje ni alertas de nivel para el flujometro.

## Persistencia

La migracion `20260905_actuadores_medicion_volumen.sql` agrega los metodos
al catalogo, el modelo YF-S201 y su metrica CAUDAL. Se ejecuta al arrancar
el backend y conserva el historial y las asignaciones.

La tabla compartida `telemetria_tanque` guarda ambos metodos:

| Metodo | Valores almacenados por lectura |
| --- | --- |
| proximidad | distancia_cm, nivel_agua_cm, porcentaje_nivel |
| flujometro | litros_riego, litros_acumulados, caudal_l_min, pulsos_riego, pulsos_por_litro |

Cada lectura guarda `metodo_medicion`. Los volumenes medidos conservan
cuatro decimales. `ejecuciones_riego.metodo_medicion` identifica como se
obtuvo el consumo de cada tramo. `ejecuciones_riego.cantidad_agua_litros`
y `riego.cantidad_agua_litros` guardan el consumo del tramo y del riego,
respectivamente. Los reportes acumulativos se reemplazan, no se suman
entre si; un OFF repetido no duplica el consumo.

El cierre local registra los litros del ciclo. Cuando el servidor cierra
la sesion antes de recibir el OFF, conserva la ultima medicion recibida;
el consumo puede excluir los pulsos posteriores a ese reporte. El estado
pendiente se reintenta mientras el equipo permanezca encendido; no hay una
cola persistente de telemetria ni confirmacion de guardado en base de datos.

Verificacion: compilar para ESP32 y ejecutar
`python -m pytest tests/test_water_measurement.py tests/test_direct_water.py tests/test_irrigation.py -q`.
La validacion fisica debe comprobar apertura/cierre, desconexion y ausencia
de flujo con el montaje real antes de usar el riego sin supervision.


## Normalización de fuentes de agua

La migración `20260906_normalizar_fuentes_agua.sql` conserva los IDs y las
referencias de cultivos y asignaciones. Los códigos persistidos son `tanque`
y `conexion_directa`; la API acepta también el alias anterior `manguera`.
Las restricciones CHECK rechazan otros tipos y configuraciones incompatibles.

- Tanque: capacidad positiva en litros y altura positiva en centímetros.
  La API usa 10 cm de seguridad cuando se omite y exige que sea menor que
  la altura total; cero es válido. La base admite NULL en la seguridad de
  registros antiguos, que el protocolo interpreta como 10 cm.
- Conexión directa: capacidad, altura y seguridad quedan en NULL.
  La medición corresponde al flujómetro del actuador, no a un tanque virtual.

La respuesta de fuentes incluye `capacidad_litros`; `capacidad_m3` se mantiene
como conversión calculada para clientes anteriores, sin duplicar almacenamiento.
La calibración por pulsos y los volúmenes permanecen en los datos de medición.

El adaptador compartido de configuración MQTT/provisionamiento envía
`tipo_fuente=manguera` a los firmwares existentes y omite dimensiones para
conexión directa. Sin fuente no inventa dimensiones, y sin fuente ni método
registrado no se infiere una medición de proximidad.

La migración es repetible y transaccional en el arranque habitual del backend.
Si hay tanques históricos sin capacidad/altura válidas, la restricción impide
la migración completa: esos datos deben corregirse con sus medidas reales.


## LCD en inventario

La migración `20260906_catalogo_lcd.sql` agrega el modelo **LCD 16x2 I2C**
como categoría `pantalla`, sin métrica. Registrar cada unidad física desde
Componentes y vincularla al dispositivo usando GPIO13 (SDA) como pin principal.
El firmware fija SCL en GPIO14 y la dirección I2C en 0x27; la asignación actual
almacena un solo pin principal. La migración agrega el modelo, no inventa stock.

`estado_bomba` sigue presente en MQTT como nombre histórico del estado lógico
de riego. `bomba_fisica_encendida` siempre es falso y no implica una salida física.


## Versión instalable

El gestor distingue `riego` (proximidad/tanque) de `riego_flujo` (conexión
directa/flujómetro). El backend rechaza iniciar una instalación de la otra
familia aunque se solicite por API. La versión `riego_flujo 1.0.0` está en
`firmware_store/esp32-flujo-1.0.0` con manifiesto, hashes y segmentos ESP32:
bootloader 0x1000, particiones 0x8000, boot_app0 0xe000 y aplicación 0x10000.
La migración `20260906_firmware_flujo.sql` registra esa versión sin retirar
la versión de tanque. Para desplegar, incluir también los cuatro binarios.

Si el monitor del flujómetro muestra `Distancia` o `BOMBA OFF (sensor sin
lectura)`, reinstalar la versión de flujo por USB desde el gestor y reenviar
la configuración de campo. Enviar configuración no reemplaza el firmware.


## Guardado de credenciales (1.0.1)

La versión de flujo 1.0.1 verifica por lectura los valores escritos en NVS
antes de responder YAKU_PROVISIONING_OK. El receptor USB reserva 4096 bytes.
Al arrancar, YAKU_CONFIG_LOADED indica que hay SSID almacenado;
YAKU_WAITING_PROVISIONING indica que falta. Esto no confirma autenticación WiFi.
El gestor espera la respuesta a 115200 baudios y conserva los campos de claves
si recibe ERROR, se desconecta el puerto o vence el plazo de confirmación.
Una instalación borra la flash: reenviar las credenciales después de instalar.


## Diagnóstico de conexión (1.0.2)

La versión 1.0.2 deja 20 segundos entre intentos WiFi y reintenta solicitar
la configuración MQTT cada 5 segundos hasta recibirla. El monitor distingue:

- YAKU_WIFI_CONNECTED: recibió una IP.
- YAKU_WIFI_DISCONNECTED reason=N: causa de desconexión reportada por ESP32.
- YAKU_MQTT_CONNECTED: conexión con el broker establecida.
- YAKU_MQTT_ERROR code=N: resultado de PubSubClient (4 credenciales incorrectas,
  5 no autorizado, negativos conexión/tiempo de espera).
- YAKU_CONFIG_RECEIVED active=1 valid=1: fuente compatible y habilitación recibidas.
- YAKU_COMMAND_RECEIVED y YAKU_VALVE_ON_GPIO25: orden recibida y GPIO activado.
- YAKU_COMMAND_REJECTED_INACTIVE_OR_CONFIG: dispositivo deshabilitado o sin configuración válida.
- YAKU_VALVE_OFF reason=sin_flujo: cierre por ausencia de pulsos.

El indicador Online de la app usa ultimo_ping reciente y se mantiene separado
del interruptor de habilitación. Una orden enviada al broker o un contador
iniciado por el servidor no prueban por sí solos la apertura física de la válvula.
La polaridad del relé sigue definida por RELE_ON/RELE_OFF según el montaje.


## Compatibilidad con ESP32-S3 (1.0.3)

Se comparó `esp32-s3.ino`: ambos conectan con WIFI_STA, SSID/clave guardados,
WiFiClientSecure, usuario/clave MQTT y el tópico individual `/config`.
Se igualó keep-alive a 60 segundos y la recepción de ACTIVE/INACTIVE del S3.
El servidor envía ahora JSON `{"funcionamiento_activo":true/false}` desde las
dos rutas de habilitación, compatible con ambos firmwares. El firmware de
flujo también acepta los mensajes de texto anteriores.

`YAKU_WIFI_CONNECTED` y `YAKU_MQTT_CONNECTED` confirman conexiones establecidas.
`YAKU_CONFIG_RECEIVED active=0 valid=1` significa conectado pero deshabilitado.
Habilitar permite recibir ON, pero por sí solo no abre la válvula: todavía
requiere fuente válida y una orden de riego. Deshabilitar cierra la válvula.
El cambio no activa equipos ni inicia riegos durante el despliegue.


## Monitor serie (1.0.4)

A 115200 baudios, el firmware muestra caudal (L/min), litros del ciclo,
acumulado desde el arranque, pulsos, estado de riego, WiFi y MQTT.
Actualiza durante el riego cada segundo, al abrir/cerrar y cada 10 segundos
en reposo. Funciona también si no hay LCD conectada. Usa las mismas variables
que la pantalla, sin modificar la medición ni el envío MQTT.

Al conectar muestra IP local, señal WiFi, servidor/puerto MQTT, Client ID y
suscripciones, conservando los códigos YAKU de diagnóstico. No imprime claves.
Ejemplo de formato (valores ilustrativos):

```text
[WiFi] Conexion establecida. IP: 192.168.0.50 | Senal: -55 dBm
[MQTT] Conexion establecida. Cliente: ESP32_Yaku_002
[Flujo] Riego: ON | Caudal: 2.50 L/min | Ciclo: 0.125 L | Acumulado: 0.125 L | Pulsos: 56
[Conexion] WiFi: conectado | MQTT: conectado | Dispositivo: habilitado
```


## Monitor y cierre de riego (1.0.5)

El monitor usa encabezado de arranque, mensajes de conexión, recepción MQTT,
activación y bloques «Ciclo de lectura» con el estilo del ESP32-S3. Las lecturas
de caudal se imprimen únicamente si `activo` es verdadero. La LCD conserva
su comportamiento. Los mensajes de conexión, habilitación y cierre permanecen
visibles aunque el dispositivo se desactive.

Al cerrar un riego se toma el conteo final de pulsos y se calcula litros_riego.
Se marca un cierre pendiente y el siguiente envío MQTT incluye estado_bomba=OFF,
los litros finales, pulsos y motivo de cierre. El monitor muestra el resumen
y «Cierre MQTT enviado» solo si mqtt.publish devuelve éxito. Un nuevo riego
no reemplaza esos valores mientras el envío pendiente falle.

Si falta conexión, el cierre se conserva en RAM y se reintenta al reconectar.
PubSubClient publica estos datos con QoS 0: éxito del envío no equivale a una
confirmación de guardado en base de datos. El pendiente no sobrevive a cortes
de alimentación. Las pruebas del backend cubren el volumen del cierre y que
los reportes repetidos no sumen dos veces el consumo.


## Retroiluminación LCD (1.0.6)

Versión compilada desde la fuente web 1.0.5, recuperada del historial Git y
validada contra source_sha256 del manifiesto publicado. El cambio funcional
es lcd.backlight() después de lcd.init(), cuando se detecta el LCD I2C 0x27.
Conserva MQTT, aprovisionamiento, habilitación lógica y cierre con litros.
No incorpora el programa de ciclos autónomos; ese archivo se conserva como
referencia en docs/referencias/esp32-flujo-autonomo-20260912.txt.

La app instala los segmentos de firmware_store/esp32-flujo-1.0.6. Cambiar solo
el .ino no actualiza un equipo ni los binarios instalables. La nueva carpeta
incluye además una copia de la fuente exacta usada para compilar.
