from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.plantaDto import PlantaCreate, UmbralPlantaSchema
from src.main.model.models import plantas
from src.main.repositories import plantaRep as data_repository
from src.main.repositories import sessionRep as session_repository


def listar_plantasServ(db: Session = None, current_user=None):
    """Obtiene el catálogo completo de plantas."""
    db_plantas = data_repository.queryListarPlantasDbPlantas(db)

    res = []
    for p in db_plantas:
        db_umbrales = data_repository.queryListarPlantasDbUmbrales(db, p)
        umbrales_list = [
            {
                "id_tipo_metrica": u.id_tipo_metrica,
                "valor_minimo": float(u.valor_minimo)
                if u.valor_minimo is not None
                else None,
                "valor_maximo": float(u.valor_maximo)
                if u.valor_maximo is not None
                else None,
            }
            for u in db_umbrales
        ]
        res.append(
            {
                "id": p.id_planta,
                "nombre": p.nombre,
                "tipo": p.tipo,
                "descripcion": p.descripcion,
                "umbrales": umbrales_list,
            }
        )
    return res


def registrar_plantaServ(payload: PlantaCreate, db: Session = None, current_user=None):
    """Registra una nueva especie de planta en el catálogo. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # Validar duplicados
    existente = data_repository.queryRegistrarPlantaExistente(db, payload)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta planta ya se encuentra registrada en el catálogo.",
        )

    nueva = plantas(
        nombre=payload.nombre, tipo=payload.tipo, descripcion=payload.descripcion
    )
    session_repository.add(db, nueva)
    session_repository.commit(db)
    session_repository.refresh(db, nueva)

    response_umbrales = []
    if payload.umbrales:
        from src.main.model.models import umbrales_planta

        for u in payload.umbrales:
            nuevo_umbral = umbrales_planta(
                id_planta=nueva.id_planta,
                id_tipo_metrica=u.id_tipo_metrica,
                valor_minimo=u.valor_minimo,
                valor_maximo=u.valor_maximo,
            )
            session_repository.add(db, nuevo_umbral)
            response_umbrales.append(
                {
                    "id_tipo_metrica": u.id_tipo_metrica,
                    "valor_minimo": u.valor_minimo,
                    "valor_maximo": u.valor_maximo,
                }
            )
        session_repository.commit(db)

    return {
        "id": nueva.id_planta,
        "nombre": nueva.nombre,
        "tipo": nueva.tipo,
        "descripcion": nueva.descripcion,
        "umbrales": response_umbrales,
    }


def actualizar_umbrales_plantaServ(
    planta_id: int,
    payload: List[UmbralPlantaSchema],
    db: Session = None,
    current_user=None,
):
    """Agrega o modifica los rangos recomendados de una planta."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    planta = data_repository.queryActualizarUmbralesPlantaPlanta(db, planta_id)
    if not planta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Planta no encontrada."
        )

    from src.main.model.models import umbrales_planta

    ids_metricas = [umbral.id_tipo_metrica for umbral in payload]
    if len(ids_metricas) != len(set(ids_metricas)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede enviar la misma métrica más de una vez.",
        )

    consulta_actuales = data_repository.queryActualizarUmbralesPlantaConsultaActuales(
        db, planta_id
    )
    if ids_metricas:
        data_repository.queryActualizarUmbralesPlantaUmbralesPlanta(
            consulta_actuales, ids_metricas
        )
    else:
        data_repository.queryActualizarUmbralesPlantaDelete(consulta_actuales)

    for umbral in payload:
        existente = data_repository.queryActualizarUmbralesPlantaExistente(
            db, planta_id, umbral
        )

        if existente:
            existente.valor_minimo = umbral.valor_minimo
            existente.valor_maximo = umbral.valor_maximo
        else:
            session_repository.add(
                db,
                umbrales_planta(
                    id_planta=planta_id,
                    id_tipo_metrica=umbral.id_tipo_metrica,
                    valor_minimo=umbral.valor_minimo,
                    valor_maximo=umbral.valor_maximo,
                ),
            )

    session_repository.commit(db)
    return payload
