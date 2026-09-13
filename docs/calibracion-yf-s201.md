# Calibracion del YF-S201 y caudal en L/s

El firmware `esp32-sensor-flujo.ino` v1.0.7 usa **450 pulsos/L como valor
nominal**, no como calibracion certificada de cada unidad. No es posible conocer
el factor real de este sensor instalado sin recoger y medir agua.

## Fundamento y fuentes

- [Seeed Studio, Water Flow Sensor](https://wiki.seeedstudio.com/Water-Flow-Sensor/):
  el apartado del YF-S201 indica 450 pulsos/L y conteo por interrupcion.
  No confundirlo con otros sensores de la misma pagina, con factores diferentes.
- [Ficha YF-S201, Rajguru Electronics](https://www.rajguruelectronics.com/Product/1668/YF-S201%2012%20Water%20Flow%20Hall%20Sensor.pdf):
  frecuencia nominal `f = 7.5 * Q`, con f en Hz y Q en L/min.
- [Si Thu, Nilar Aung y Ko Ko Maung, 2018: A Calibration Technique for Water Flow Sensor YF-S201](https://www.ijtrd.com/papers/IJTRD17965.pdf):
  compara el volumen recogido y el tiempo con las lecturas y ajusta el factor.
  El articulo tiene una errata en la equivalencia por pulso: 1/450 L son
  aproximadamente **2.22 mL**, no 22.3 mL.

Consultadas el 12 de septiembre de 2026. A partir de esa relacion:

```
K [pulsos/L] = pulsos contados / litros reales recogidos
volumen [L] = pulsos / K
caudal [L/s] = pulsos_del_intervalo * 1000 / (K * intervalo_ms)
```

Se usa el intervalo realmente transcurrido, aunque el bucle tarde mas de un
segundo. El volumen se obtiene del contador, sin sumar caudales redondeados.
Ejemplo nominal: 450 pulsos en 10 s equivalen a 1 L y 0.1 L/s.

## Procedimiento de campo

1. Instalar segun la flecha del sensor, mantener la tuberia llena y purgar aire.
   Mantener la misma orientacion y condiciones durante calibracion y uso.
2. Hacer un riego manual supervisado desde la app, recogiendo toda la salida
   en un recipiente graduado. Usar, por ejemplo, 5 a 10 L para reducir el efecto
   relativo de la resolucion del recipiente. No usar el volumen mostrado por el
   propio sensor como referencia.
3. Detener el riego y anotar `Pulsos=...` del mensaje final del monitor serie,
   el volumen real y el tiempo. Esperar el envio del cierre MQTT.
4. Repetir al menos tres veces al caudal habitual; validar tambien a otros
   caudales de uso. Para un factor unico, dividir la suma de pulsos entre la suma
   de litros. Si el error cambia mucho con el caudal, un unico factor no basta
   para garantizar precision en todo el rango.
5. Con la valvula detenida, enviar una linea JSON por el monitor serie, seguida
   de salto de linea. Ejemplo ilustrativo, **sustituir por medidas reales**:

   ```json
   {"accion":"CALIBRAR_FLUJO","pulsos":4620,"litros_reales":10.0}
   ```

   La respuesta esperada es `YAKU_CALIBRATION_OK K=462.0000 pulsos/L`.
   El factor se verifica y guarda en NVS, sobrevive a reinicios y se aplica
   desde el proximo riego. No cambia volumenes de ciclos anteriores ni abre
   la valvula. Se rechaza durante riego o con un cierre pendiente de publicar.
6. Repetir una recogida independiente y calcular
   `error_% = 100 * (litros_sensor - litros_reales) / litros_reales`.
   Registrar fecha, factor, orientacion, caudal y errores de validacion.

Los limites de configuracion 100 a 2000 pulsos/L son defensivos; no representan
el rango garantizado del fabricante. El filtro de 300 us ya existente se
conserva; no debe aumentarse para ocultar ruido sin verificar pulsos perdidos.

## Unidades e instalacion

LCD y monitor serie muestran **L/s**. El volumen y el resumen final siguen en
**litros**. MQTT agrega `caudal_l_s`; mantiene `caudal_l_min = caudal_l_s * 60`
para los consumidores y la columna historica que todavia usan L/min. Nunca se
almacenan L/s bajo un nombre que significa L/min. Cada ciclo publica el factor
con el que se calculo su volumen, incluso si despues se cambia la calibracion.

Desde v1.0.8, el LCD muestra ambos valores juntos en la segunda fila:

```text
Riego directo ON
 27.07L 0.123L/s
```

El volumen es el consumido en el evento actual, no el acumulado historico.
Al cerrar, conserva el volumen final y muestra caudal cero; al iniciar el
siguiente evento, el volumen comienza en cero. Las dos filas se sobrescriben
completas sin borrar la pantalla en cada lectura. Para volumenes grandes se
reducen decimales; si un valor excede su columna, se indica con `#` sin invadir
la otra unidad. Esto solo afecta la presentacion, no el calculo ni MQTT.

Editar el `.ino` no modifica los binarios de versiones anteriores. Es necesario
instalar un binario compilado de esta version para observar estos cambios.
