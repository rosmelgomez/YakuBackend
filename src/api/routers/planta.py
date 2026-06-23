from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db.models import plantas
from ...schemas.planta import PlantaResponseModel, PlantaCreate, UmbralPlantaSchema
from ...core.bff_auth import get_current_user_or_bff
from ..dependencies import get_db

router = APIRouter(prefix="/plantas", tags=["Catálogo de Plantas"])



@router.get("", response_model=List[PlantaResponseModel])
def listar_plantas(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene el catálogo completo de plantas."""
    db_plantas = db.query(plantas).order_by(plantas.nombre.asc()).all()
    from ...db.models import umbrales_planta

    res = []
    for p in db_plantas:
        db_umbrales = db.query(umbrales_planta).filter(umbrales_planta.id_planta == p.id_planta).all()
        umbrales_list = [
            {
                "id_tipo_metrica": u.id_tipo_metrica,
                "valor_minimo": float(u.valor_minimo) if u.valor_minimo is not None else None,
                "valor_maximo": float(u.valor_maximo) if u.valor_maximo is not None else None
            }
            for u in db_umbrales
        ]
        res.append({
            "id": p.id_planta,
            "nombre": p.nombre,
            "tipo": p.tipo,
            "descripcion": p.descripcion,
            "umbrales": umbrales_list
        })
    return res


@router.post("", response_model=PlantaResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_planta(
    payload: PlantaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra una nueva especie de planta en el catálogo. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    # Validar duplicados
    existente = db.query(plantas).filter(plantas.nombre == payload.nombre).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta planta ya se encuentra registrada en el catálogo."
        )

    nueva = plantas(
        nombre=payload.nombre,
        tipo=payload.tipo,
        descripcion=payload.descripcion
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)

    response_umbrales = []
    if payload.umbrales:
        from ...db.models import umbrales_planta
        for u in payload.umbrales:
            nuevo_umbral = umbrales_planta(
                id_planta=nueva.id_planta,
                id_tipo_metrica=u.id_tipo_metrica,
                valor_minimo=u.valor_minimo,
                valor_maximo=u.valor_maximo
            )
            db.add(nuevo_umbral)
            response_umbrales.append({
                "id_tipo_metrica": u.id_tipo_metrica,
                "valor_minimo": u.valor_minimo,
                "valor_maximo": u.valor_maximo
            })
        db.commit()

    return {
        "id": nueva.id_planta,
        "nombre": nueva.nombre,
        "tipo": nueva.tipo,
        "descripcion": nueva.descripcion,
        "umbrales": response_umbrales
    }


@router.put("/{planta_id}/umbrales", response_model=List[UmbralPlantaSchema])
def actualizar_umbrales_planta(
    planta_id: int,
    payload: List[UmbralPlantaSchema],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Agrega o modifica los rangos recomendados de una planta."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    planta = db.query(plantas).filter(plantas.id_planta == planta_id).first()
    if not planta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planta no encontrada.")

    from ...db.models import umbrales_planta

    ids_metricas = [umbral.id_tipo_metrica for umbral in payload]
    if len(ids_metricas) != len(set(ids_metricas)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede enviar la misma métrica más de una vez."
        )

    consulta_actuales = db.query(umbrales_planta).filter(umbrales_planta.id_planta == planta_id)
    if ids_metricas:
        consulta_actuales.filter(~umbrales_planta.id_tipo_metrica.in_(ids_metricas)).delete(synchronize_session=False)
    else:
        consulta_actuales.delete(synchronize_session=False)

    for umbral in payload:
        existente = db.query(umbrales_planta).filter(
            umbrales_planta.id_planta == planta_id,
            umbrales_planta.id_tipo_metrica == umbral.id_tipo_metrica
        ).first()

        if existente:
            existente.valor_minimo = umbral.valor_minimo
            existente.valor_maximo = umbral.valor_maximo
        else:
            db.add(umbrales_planta(
                id_planta=planta_id,
                id_tipo_metrica=umbral.id_tipo_metrica,
                valor_minimo=umbral.valor_minimo,
                valor_maximo=umbral.valor_maximo
            ))

    db.commit()
    return payload
