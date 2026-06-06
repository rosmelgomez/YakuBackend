from typing import Generator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..Model import crud
from ..Model.conexion import SessionLocal
from ..Model.schemas import ControlAguaModel, RiegoDatosModel

router = APIRouter(prefix="/riego", tags=["Riego"])


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/datos")
def guardar_datos_riego(
    data: RiegoDatosModel,
    db: Session = Depends(get_db),
):
    try:
        crud.crear_datos_riego(db, data)
        return {"status": "ok", "message": "Datos de riego guardados correctamente"}
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al guardar los datos de riego") from exc



@router.get("/lista_humedad_suelo")
def obtener_humedad_suelo(db: Session = Depends(get_db)):
    return crud.listar_humedad_suelo(db)


@router.get("/lista_humedad_ambiente")
def obtener_humedad_ambiente(db: Session = Depends(get_db)):
    return crud.listar_humedad_ambiente(db)


@router.get("/lista_temperatura_ambiente")
def obtener_temperatura_ambiente(db: Session = Depends(get_db)):
    return crud.listar_temperatura_ambiente(db)


@router.get("/lista_temperatura_suelo")
def obtener_temperatura_suelo(db: Session = Depends(get_db)):
    return crud.listar_temperatura_suelo(db)


@router.post("/control_agua")
def guardar_control_agua(data: ControlAguaModel, db: Session = Depends(get_db)):
    try:
        registro = crud.crear_control_agua(
            db=db,
            sensor=data.sensor,
            distancia_cm=data.distancia_cm,
            altura_referencia_cm=data.altura_referencia_cm,
            estado_bomba=data.estado_bomba,
            fecha=data.fecha,
        )
        return {
            "status": "ok",
            "message": "Control de agua guardado correctamente",
            "id": registro.id,
            "nivel_agua_cm": registro.nivel_agua_cm,
            "porcentaje_nivel": registro.porcentaje_nivel,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al guardar el control de agua") from exc


@router.get("/lista_control_agua")
def obtener_control_agua(db: Session = Depends(get_db)):
    return crud.listar_control_agua(db)




