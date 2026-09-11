# YakuESP32

Backend FastAPI y firmwares ESP32 del sistema Yaku.

## Distribución del proyecto

La organización sigue la estructura de `essalud-ggi-tmi-backend`:

```text
app.py                         # Configura FastAPI y registra los routers
main.py                        # Compatibilidad con main:app
src/
  main/
    controller/                # Endpoints HTTP
    core/                      # Configuración, seguridad y dependencias
    db/                        # Conexión y sesiones de PostgreSQL
      databaseConexion.py
    dtos/                      # Modelos de entrada y salida Pydantic
    model/                     # Entidades SQLAlchemy
    repositories/              # Consultas y persistencia por módulo
    service/                   # Lógica de negocio y entrenamiento ML
      notifications/           # Alertas, correo, Web Push y WebSocket
    tasks/                     # Suscriptor MQTT y tareas programadas
  resources/
    migrations/                # Migraciones SQL
    ml_artifacts/              # Datasets, modelos y reporte de entrenamiento
    yaku_schema.sql
    yaku_data.sql
tests/                         # Pruebas automatizadas
firmware_store/                # Binarios y versiones OTA
```

Los imports internos usan `src.main`. Cada petición sigue el flujo
`controller → service → repositories → PostgreSQL`:

- Los controladores conservan las rutas, los DTOs de entrada/salida y las dependencias
  de FastAPI; delegan la operación a una función de servicio con sufijo `Serv`.
- Los servicios validan permisos y reglas de negocio, coordinan el riego,
  las notificaciones y el entrenamiento, y deciden cuándo confirmar o revertir
  una transacción.
- Los repositorios contienen las consultas SQLAlchemy y la persistencia.
  `sessionRep.py` reúne las operaciones de sesión compartidas. Los repositorios
  no importan servicios ni controladores.
- Los DTOs contienen las definiciones Pydantic de su propio dominio, incluidas
  las validaciones y los modelos anidados. `model/models.py` define las entidades
  SQLAlchemy.

Por ejemplo, `apiAlmacen.registrar_almacen` delega en
`almacenServ.registrar_almacenServ`; el servicio valida el rol y consulta
`almacenRep` antes de guardar el almacén. Los controladores no ejecutan consultas
ni definen clases Pydantic.

Los nombres de archivos siguen las convenciones del proyecto de referencia:

| Capa | Patrón | Ejemplos en Yaku |
| --- | --- | --- |
| Controladores | `api<Modulo>.py` | `apiUsuario.py`, `apiDashboard.py`, `apiTelemetria.py` |
| Servicios | `<modulo>Serv.py` | `dashboardServ.py`, `irrigationServ.py`, `mlTrainingServ.py` |
| Repositorios | `<modulo>Rep.py` | `almacenRep.py`, `telemetriaRep.py`, `mlRep.py` |
| DTOs | `<modulo>Dto.py` | `usuarioDto.py`, `telemetriaDto.py`, `dashboardDto.py` |
| Configuración | `<modulo>Config.py` | `yakuConfig.py`, `notificationConfig.py` |
| Base de datos | `database<Responsabilidad>.py` | `databaseConexion.py`, `databaseSession.py` |
| Entidades | `models.py` | `model/models.py` |

Los módulos adicionales usan nombres como `mqttSubscriberTask.py`,
`schedulerTask.py`, `bffAuth.py` y `bffTokens.py`. Los archivos `__init__.py`
conservan el nombre requerido por Python.

`core/application.py` administra el ciclo de vida y llama a `bootstrapServ.py`;
`bootstrapRep.py` prepara el esquema y ejecuta las migraciones. Las comprobaciones
de salud y el WebSocket se registran en `apiSistema.py`.

`mqttSubscriberTask.py` administra la conexión al broker y delega los mensajes en
`mqttServ.py`. `schedulerTask.py` administra el bucle del planificador y delega las
reglas de riego en `schedulerServ.py`. La lógica de telemetría que abre, pausa o
cierra riegos pertenece a `telemetriaServ.py`.

Los recursos SQL se resuelven desde la ubicación del proyecto. Los sketches,
notebooks, scripts de carga y almacenamiento OTA mantienen su ubicación en la raíz.

## Rol en la arquitectura

```text
Next.js -> FastAPI -> PostgreSQL
ESP32 -> MQTT -> FastAPI -> PostgreSQL
FastAPI -> MQTT -> ESP32
```

FastAPI es el unico servicio que debe conectarse a PostgreSQL. Next.js consume esta API mediante HTTP y WebSocket.

## Ejecutar backend

1. Copia `.env.example` a `.env`.
2. Configura PostgreSQL, MQTT, autenticacion BFF, SMTP y VAPID.
3. Instala dependencias:

```bash
pip install -r requirements.txt
```

4. Ejecuta:

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Los despliegues existentes pueden seguir usando `uvicorn main:app`.

## Verificar la separación de capas

```bash
python -m pytest -q
```

Las pruebas incluyen límites de dependencias entre capas y flujos HTTP de registro,
cambio de contraseña, permisos, almacenes, umbrales de plantas y respaldos. Estos
flujos usan SQLite temporal y sustituyen los servicios externos; no ejecutan las
migraciones de arranque ni conectan al broker MQTT.

## MQTT

Topics principales:

- `yaku/riego/datos`: lecturas del ESP32 de sensores.
- `yaku/tanque/datos`: telemetria del tanque/bomba.
- `yaku/riego/comando`: comandos de control hacia el ESP32.
- `yaku/dispositivo/{client_id}/config`: configuracion dinamica hacia dispositivos.
- `yaku/dispositivo/{client_id}/config/req`: solicitud de configuracion desde dispositivos.

## Seguridad

Next.js firma tokens BFF de corta duracion con `BFF_JWT_SECRET`; el mismo secreto debe configurarse en ambos proyectos. FastAPI valida su firma, audiencia y expiracion antes de consultar nuevamente al usuario.

Para los sketches, copia `secrets.example.h` como `secrets.h`. Este ultimo esta ignorado por Git. Usa credenciales MQTT distintas por dispositivo y ACL limitadas a sus topicos.

Antes de produccion configura `APP_ENV=production`, `COOKIE_SECURE=true`, origenes HTTPS explicitos y ejecuta `pytest`, `pip-audit` y `npm audit`. Si una credencial estuvo en codigo fuente, rotala en el proveedor; borrarla del archivo no invalida la credencial antigua.

## Frontend y backend en servicios distintos

Publica FastAPI con HTTPS y soporte WebSocket. En este servicio configura:

```env
APP_ENV=production
ALLOWED_ORIGINS=https://app.example.com
BFF_JWT_SECRET=<secreto-compartido>
```

En Next.js, `FASTAPI_API_URL` debe apuntar a este servicio y
`NEXT_PUBLIC_WS_URL` debe usar la misma URL con `wss://` y la ruta
`/ws/alertas`. `BFF_JWT_SECRET` debe coincidir exactamente en ambos servicios.

## Entrenamiento de modelos

El entrenamiento reproducible de Random Forest y XGBoost está en `src/main/service/mlTrainingServ.py`.
Genera los modelos de tomate, chilli, papa, zanahoria y trigo, además de
`src/resources/ml_artifacts/training_report.json`:

```powershell
python -m src.main.service.mlTrainingServ --algorithm all --crop all
```

También permite entrenar una sola combinación, por ejemplo:

```powershell
python -m src.main.service.mlTrainingServ --algorithm xgb --crop tomato
```

El dataset actual no contiene decisiones reales de riego etiquetadas. Las etiquetas
se derivan de reglas explícitas por cultivo; los resultados deben validarse con datos
de campo antes de habilitar control automático en producción.
