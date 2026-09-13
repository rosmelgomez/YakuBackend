# Canales de Notificación y Criterios de Uso en Yaku

Este documento establece la arquitectura y directrices oficiales de distribución de mensajes y alertas a través de los tres canales de comunicación de la plataforma Yaku:

| Canal | Uso recomendado |
|---|---|
| **Dentro de la app** | Historial de riegos, inicio y finalización, alertas, recuperaciones y cambios de estado |
| **Push del dispositivo, con permiso** | Problemas que requieren atención: riego fallido, interrupción, parada sin confirmar o desconexión durante el riego |
| **Correo** | Verificación de cuenta, recuperación de contraseña y avisos importantes de seguridad |

---

## 1. Dentro de la App (Panel Yaku & WebSockets)

- **Objetivo:** Informar al usuario en tiempo real sobre el funcionamiento continuo de sus parcelas mientras tiene la plataforma abierta o la consulta.
- **Eventos que gestiona:**
  - Historial consolidado de riegos (fechas, volumen acumulado y duración).
  - Notificaciones de inicio y finalización de ciclo de riego (manual, programado o ML predictivo).
  - Alertas automáticas por cruce de umbrales en sensores (humedad de suelo, humedad ambiente, temperatura).
  - Recuperaciones cuando una métrica vuelve a situarse dentro de su rango normal.
  - Cambios de estado en actuadores (bomba, electroválvula, estado online/offline).
- **Mecanismo técnico:**
  - Comunicación bidireccional mediante WebSocket en `/ws/alertas`.
  - El backend despacha eventos usando `manager.broadcast()` y `broadcast_ws_event()`.
  - Los eventos se registran con `canal = 'dashboard'` en la base de datos para visualización en el historial de alertas y campana de avisos.

---

## 2. Push del Dispositivo (Web Push con Permiso)

- **Objetivo:** Notificar de inmediato al agricultor en la pantalla de su dispositivo móvil o computadora ante **problemas críticos que requieran su atención e intervención**.
- **Eventos que gestiona:**
  - **Riego fallido:** Fallos al intentar accionar el actuador o ausencia de respuesta del hardware.
  - **Interrupción:** Interrupción imprevista de un ciclo activo antes de alcanzar su meta o tiempo planeado.
  - **Parada sin confirmar:** Órdenes de apagado emitidas por el sistema que no son confirmadas por el actuador en el tiempo límite.
  - **Desconexión durante el riego:** Pérdida de comunicación o ping del dispositivo mientras un ciclo de bombeo se encuentra en ejecución.
- **Mecanismo técnico:**
  - Estándar Web Push (VAPID / RFC 8291).
  - Requiere consentimiento explícito del navegador (`Notification.requestPermission()`) y suscripción persistida en `suscripciones_push`.
  - Configurable a nivel de alerta crítica con `canal_push = TRUE` en `configuracion_notificaciones`.
  - Despacho directo mediante la función de servicio `notificar_problema_riego()`.

---

## 3. Correo (Email Transaccional)

- **Objetivo:** Canal seguro y formal para la administración de identidad, acceso y seguridad de la cuenta del usuario.
- **Eventos que gestiona:**
  - Verificación y activación de cuenta al registrarse.
  - Solicitud de restablecimiento y recuperación de contraseña.
  - Avisos importantes de seguridad (cambios de credenciales, accesos sospechosos o modificaciones críticas de perfil).
- **Directriz de diseño:**
  - **No se envía correo por variaciones rutinarias de sensores:** Los umbrales de humedad o temperatura no saturan la bandeja de entrada del agricultor (`canal_email` deshabilitado por defecto para métricas agronómicas).
