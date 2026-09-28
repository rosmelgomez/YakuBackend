"""El riego que ejecuta el ML envía al ESP32 cuánto tiempo regar.

El scheduler (schedulerServ._check_ml_cooldown_and_irrigate) inicia el riego con
start_irrigation(irrigation_type="automatico_ml") sin duración explícita: se usa
la duración configurada para el cultivo. Esa duración viaja en el comando ON
(`duracion_seg`), y el firmware la usa para su cronómetro local, de modo que
cierra a tiempo aunque se corte la conexión.
"""

import json

from src.main.model.models import configuracion_control, configuracion_actuador, riego
from src.main.service.irrigationServ import start_irrigation
from test_mqtt_ingesta import _asignacion, _escenario_base


TOPIC_COMANDO = "yaku/riego/comando/ESP32_TEST"


def _actuador(db, topic_sub=TOPIC_COMANDO):
    usuario, fuente, cultivo, disp = _escenario_base(db, metodo_medicion="proximidad")
    disp.topic_sub = topic_sub
    asig = _asignacion(db, usuario, cultivo, disp, fuente=fuente)
    db.add(configuracion_actuador(id_asignacion=asig.id))
    db.commit()
    return asig


def _riego_ml(db, asig):
    return start_irrigation(db=db, assignment=asig, irrigation_type="automatico_ml")


def _comandos(publicados, topic=TOPIC_COMANDO):
    # El backend también publica el estado de la bomba en otro tópico.
    return [json.loads(payload) for t, payload in publicados if t == topic]


def test_riego_ml_envia_la_duracion_configurada_al_esp32(db, mqtt_publicado):
    asig = _actuador(db)
    db.add(configuracion_control(
        id_usuario=asig.id_usuario, id_cultivo=asig.id_cultivo, duracion_riego_max_seg=900
    ))
    db.commit()

    sesion = _riego_ml(db, asig)

    assert _comandos(mqtt_publicado) == [{"accion": "ON", "duracion_seg": 900, "id_riego": sesion.id}]

    db.expire_all()
    guardada = db.get(riego, sesion.id)
    assert guardada.tipo_riego == "automatico_ml"
    assert guardada.duracion_segundos == 900


def test_riego_ml_sin_configuracion_usa_10_minutos(db, mqtt_publicado):
    asig = _actuador(db)

    sesion = _riego_ml(db, asig)

    assert _comandos(mqtt_publicado) == [{"accion": "ON", "duracion_seg": 600, "id_riego": sesion.id}]
