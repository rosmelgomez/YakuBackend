from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.feedbackDto import (
    FeedbackCreate,
    FeedbackKpisResponse,
    FeedbackPreguntaCreate,
    FeedbackPreguntaKpi,
    FeedbackPreguntaResponse,
    FeedbackPreguntaUpdate,
    FeedbackResponse,
    FeedbackRespuestaResponse,
    FeedbackRespuestaTextoItem,
)
from src.main.model.models import (
    feedback_agricultores,
    feedback_preguntas,
    feedback_respuestas,
    logs_sistema,
)
from src.main.repositories import feedbackRep as data_repository
from src.main.repositories import sessionRep as session_repository

DEFAULT_FEEDBACK_QUESTIONS = [
    {
        "pregunta": "¿Con qué frecuencia utilizas la plataforma Yaku?",
        "tipo": "select",
        "obligatoria": True,
        "opciones": [
            "Varias veces al día",
            "Una vez al día",
            "Varios días a la semana",
            "Una vez a la semana",
            "Menos de una vez a la semana",
        ],
        "orden": 1,
        "activo": True,
    },
    {
        "pregunta": "¿Cómo valorarías la utilidad del sistema de alertas?",
        "tipo": "rating",
        "obligatoria": True,
        "opciones": None,
        "orden": 2,
        "activo": True,
    },
    {
        "pregunta": "¿Las recomendaciones de riego se han ajustado a las necesidades reales de tu cultivo?",
        "tipo": "rating",
        "obligatoria": True,
        "opciones": None,
        "orden": 3,
        "activo": True,
    },
    {
        "pregunta": "¿Qué aspecto mejorarías de la plataforma?",
        "tipo": "text",
        "obligatoria": False,
        "opciones": None,
        "orden": 4,
        "activo": True,
    },
    {
        "pregunta": "¿Recomendarías Yaku a otros agricultores?",
        "tipo": "rating",
        "obligatoria": True,
        "opciones": None,
        "orden": 5,
        "activo": True,
    },
    {
        "pregunta": "¿Qué funcionalidad usas con más frecuencia?",
        "tipo": "select",
        "obligatoria": False,
        "opciones": ["Control de riego", "Sensores", "Alertas", "Modelos IA"],
        "orden": 6,
        "activo": False,
    },
]


def _require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos de administrador requeridos",
        )


def _require_farmer(current_user) -> None:
    if current_user.id_rol != 2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo agricultores pueden registrar feedback",
        )


def _ensure_default_questions(db: Session) -> None:
    if data_repository.queryEnsureDefaultQuestionsFeedbackPreguntas(db) > 0:
        return
    for item in DEFAULT_FEEDBACK_QUESTIONS:
        session_repository.add(
            db,
            feedback_preguntas(
                pregunta=item["pregunta"],
                tipo=item["tipo"],
                obligatoria=item["obligatoria"],
                opciones=item["opciones"],
                orden=item["orden"],
                activo=item["activo"],
            ),
        )
    session_repository.commit(db)


def _question_response(item: feedback_preguntas) -> FeedbackPreguntaResponse:
    return FeedbackPreguntaResponse(
        id=item.id,
        pregunta=item.pregunta,
        tipo=item.tipo or "rating",
        obligatoria=item.obligatoria if item.obligatoria is not None else True,
        opciones=item.opciones,
        descripcion=item.descripcion,
        orden=item.orden,
        activo=item.activo,
        fecha_registro=item.fecha_registro,
        actualizado_en=item.actualizado_en,
    )


def _feedback_response(item: feedback_agricultores) -> FeedbackResponse:
    return FeedbackResponse(
        id=item.id,
        id_usuario=item.id_usuario,
        id_cultivo=item.id_cultivo,
        cultivo_nombre=item.cultivo.nombre_planta if item.cultivo else None,
        modulo=item.modulo,
        tipo=item.tipo,
        calificacion=item.calificacion,
        mensaje=item.mensaje,
        estado=item.estado,
        fecha=item.fecha,
        respuestas=[
            FeedbackRespuestaResponse(
                id=respuesta.id,
                id_pregunta=respuesta.id_pregunta,
                pregunta=respuesta.pregunta.pregunta
                if respuesta.pregunta
                else "Pregunta no disponible",
                tipo=respuesta.pregunta.tipo if respuesta.pregunta and respuesta.pregunta.tipo else "rating",
                calificacion=respuesta.calificacion,
                respuesta_texto=respuesta.respuesta_texto,
            )
            for respuesta in sorted(
                item.respuestas,
                key=lambda respuesta: (
                    respuesta.pregunta.orden if respuesta.pregunta else 0
                ),
            )
        ],
    )


def crear_feedbackServ(data: FeedbackCreate, db: Session = None, current_user=None):
    _require_farmer(current_user)

    cultivo = None
    if data.id_cultivo is not None:
        cultivo = data_repository.queryCrearFeedbackCultivo(db, data, current_user)
        if not cultivo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cultivo no encontrado"
            )

    question_ids = [respuesta.id_pregunta for respuesta in data.respuestas]
    if len(question_ids) != len(set(question_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se permiten respuestas duplicadas",
        )

    preguntas = data_repository.queryCrearFeedbackPreguntas(db, question_ids)
    preguntas_map = {p.id: p for p in preguntas}
    if len(preguntas) != len(question_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Una o mas preguntas no estan activas",
        )

    for resp in data.respuestas:
        p = preguntas_map[resp.id_pregunta]
        p_tipo = p.tipo or "rating"
        if p_tipo == "rating":
            if resp.calificacion is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"La pregunta '{p.pregunta}' requiere una calificación numérica",
                )
        elif p_tipo in ("text", "select"):
            if p.obligatoria and not (resp.respuesta_texto and resp.respuesta_texto.strip()):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"La pregunta '{p.pregunta}' es obligatoria",
                )

    calificaciones = [
        resp.calificacion for resp in data.respuestas if resp.calificacion is not None
    ]
    promedio = round(sum(calificaciones) / len(calificaciones)) if calificaciones else 5

    comentario = data.comentario
    if not comentario:
        text_answers = [
            f"{preguntas_map[r.id_pregunta].pregunta}: {r.respuesta_texto}"
            for r in data.respuestas
            if r.respuesta_texto
        ]
        comentario = " | ".join(text_answers) if text_answers else "Valoración registrada"

    item = feedback_agricultores(
        id_usuario=current_user.id_usuario,
        id_cultivo=cultivo.id_cultivo if cultivo else None,
        modulo="Encuesta del sistema",
        tipo="encuesta",
        calificacion=promedio,
        mensaje=comentario[:1200],
    )
    session_repository.add(db, item)
    session_repository.flush(db)

    for respuesta in data.respuestas:
        session_repository.add(
            db,
            feedback_respuestas(
                id_feedback=item.id,
                id_pregunta=respuesta.id_pregunta,
                calificacion=respuesta.calificacion,
                respuesta_texto=respuesta.respuesta_texto,
            ),
        )

    session_repository.add(
        db,
        logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="crear_feedback",
            modulo="feedback",
            descripcion=f"Encuesta de feedback registrada con promedio {promedio}/5",
        ),
    )
    session_repository.commit(db)
    session_repository.refresh(db, item)
    return _feedback_response(item)


def listar_feedback_propiosServ(db: Session = None, current_user=None):
    items = data_repository.queryListarFeedbackPropiosItems(db, current_user)
    return [_feedback_response(item) for item in items]


def listar_preguntas_feedbackServ(
    incluir_inactivas: bool = False, db: Session = None, current_user=None
):
    _ensure_default_questions(db)
    query = data_repository.queryListarPreguntasFeedbackQuery(db)
    if not incluir_inactivas or current_user.id_rol != 1:
        query = data_repository.queryListarPreguntasFeedbackQuery2(query)
    return [
        _question_response(item)
        for item in data_repository.queryListarPreguntasFeedbackFeedbackPreguntas(query)
    ]


def crear_pregunta_feedbackServ(
    data: FeedbackPreguntaCreate, db: Session = None, current_user=None
):
    _require_admin(current_user)
    item = feedback_preguntas(
        pregunta=data.pregunta,
        tipo=data.tipo,
        obligatoria=data.obligatoria,
        opciones=data.opciones,
        descripcion=data.descripcion,
        orden=data.orden,
        activo=data.activo,
    )
    session_repository.add(db, item)
    session_repository.commit(db)
    session_repository.refresh(db, item)
    return _question_response(item)


def actualizar_pregunta_feedbackServ(
    pregunta_id: int,
    data: FeedbackPreguntaUpdate,
    db: Session = None,
    current_user=None,
):
    _require_admin(current_user)
    item = data_repository.queryActualizarPreguntaFeedbackItem(db, pregunta_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pregunta no encontrada"
        )

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    session_repository.commit(db)
    session_repository.refresh(db, item)
    return _question_response(item)


def eliminar_pregunta_feedbackServ(
    pregunta_id: int,
    db: Session = None,
    current_user=None,
):
    _require_admin(current_user)
    item = data_repository.queryActualizarPreguntaFeedbackItem(db, pregunta_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pregunta no encontrada"
        )

    respuestas_count = data_repository.queryRespuestasPorPreguntaCount(db, pregunta_id)
    if respuestas_count > 0:
        item.activo = False
        session_repository.commit(db)
        return {"message": "Pregunta desactivada debido a que tiene respuestas históricas", "desactivada": True}

    session_repository.delete(db, item)
    session_repository.commit(db)
    return {"message": "Pregunta eliminada correctamente", "eliminada": True}


def obtener_kpis_feedbackServ(db: Session = None, current_user=None) -> FeedbackKpisResponse:
    _require_admin(current_user)
    _ensure_default_questions(db)

    total_feedbacks = data_repository.queryTotalFeedbacksCount(db)
    all_feedbacks = data_repository.queryAllFeedbackAgricultores(db)
    all_respuestas = data_repository.queryAllFeedbackRespuestas(db)
    preguntas = data_repository.queryAllPreguntas(db)

    preguntas_activas = sum(1 for p in preguntas if p.activo)
    preguntas_totales = len(preguntas)

    calificaciones_globales = [
        fb.calificacion for fb in all_feedbacks if fb.calificacion is not None
    ]
    promedio_general = (
        round(sum(calificaciones_globales) / len(calificaciones_globales), 2)
        if calificaciones_globales
        else 0.0
    )

    respuestas_por_pregunta: dict[int, list] = {}
    for resp in all_respuestas:
        respuestas_por_pregunta.setdefault(resp.id_pregunta, []).append(resp)

    kpis_preguntas: list[FeedbackPreguntaKpi] = []
    tasas_completitud: list[float] = []

    for p in preguntas:
        p_resps = respuestas_por_pregunta.get(p.id, [])
        total_p_resps = len(p_resps)
        tasa_porcentaje = (
            round((total_p_resps / total_feedbacks) * 100, 1)
            if total_feedbacks > 0
            else 0.0
        )
        tasas_completitud.append(tasa_porcentaje)

        tipo = p.tipo or "rating"
        promedio_cal = None
        dist_cal = None
        pct_positivas = None
        dist_opc = None
        opc_mas_votada = None
        longitud_prom = None
        ultimas_resp_texto = None

        if tipo == "rating":
            ratings = [r.calificacion for r in p_resps if r.calificacion is not None]
            if ratings:
                promedio_cal = round(sum(ratings) / len(ratings), 2)
                dist_cal = {str(star): ratings.count(star) for star in range(1, 6)}
                positivas = sum(1 for r in ratings if r >= 4)
                pct_positivas = round((positivas / len(ratings)) * 100, 1)
            else:
                promedio_cal = 0.0
                dist_cal = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
                pct_positivas = 0.0

        elif tipo == "select":
            opciones_config = p.opciones or []
            counts_opc = {opc: 0 for opc in opciones_config}
            for r in p_resps:
                txt = (r.respuesta_texto or "").strip()
                if txt:
                    counts_opc[txt] = counts_opc.get(txt, 0) + 1

            dist_opc = counts_opc
            if counts_opc and any(v > 0 for v in counts_opc.values()):
                opc_mas_votada = max(counts_opc.items(), key=lambda x: x[1])[0]
            elif opciones_config:
                opc_mas_votada = opciones_config[0]
            else:
                opc_mas_votada = None

        elif tipo == "text":
            text_items = [
                r for r in p_resps if r.respuesta_texto and r.respuesta_texto.strip()
            ]
            if text_items:
                longitudes = [len(r.respuesta_texto.strip()) for r in text_items]
                longitud_prom = round(sum(longitudes) / len(longitudes), 1)
                ultimas_resp_texto = [
                    FeedbackRespuestaTextoItem(
                        texto=r.respuesta_texto.strip(),
                        fecha=r.fecha,
                        calificacion_general=r.feedback.calificacion
                        if r.feedback
                        else None,
                    )
                    for r in text_items[:10]
                ]
            else:
                longitud_prom = 0.0
                ultimas_resp_texto = []

        kpis_preguntas.append(
            FeedbackPreguntaKpi(
                id_pregunta=p.id,
                pregunta=p.pregunta,
                tipo=tipo,
                obligatoria=p.obligatoria if p.obligatoria is not None else True,
                activo=p.activo,
                orden=p.orden,
                total_respuestas=total_p_resps,
                tasa_respuesta_porcentaje=tasa_porcentaje,
                promedio_calificacion=promedio_cal,
                distribucion_calificacion=dist_cal,
                porcentaje_positivas=pct_positivas,
                distribucion_opciones=dist_opc,
                opcion_mas_votada=opc_mas_votada,
                longitud_promedio=longitud_prom,
                ultimas_respuestas_texto=ultimas_resp_texto,
            )
        )

    tasa_promedio_general = (
        round(sum(tasas_completitud) / len(tasas_completitud), 1)
        if tasas_completitud
        else 0.0
    )

    return FeedbackKpisResponse(
        total_feedbacks=total_feedbacks,
        promedio_general=promedio_general,
        preguntas_activas=preguntas_activas,
        preguntas_totales=preguntas_totales,
        tasa_completitud_promedio=tasa_promedio_general,
        preguntas_kpis=kpis_preguntas,
    )
