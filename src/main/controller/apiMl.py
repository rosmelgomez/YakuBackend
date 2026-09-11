from typing import Any, List

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.mlDto import (
    DbTrainingRequest,
    ModelInfo,
    ModelSelectionResponse,
    PrediccionRiegoModel,
)
from src.main.service import mlServ

router = APIRouter(prefix="/ml", tags=["Machine Learning"])


@router.get("/models", response_model=List[ModelInfo])
def listar_modelos(
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Lista modelos de ML registrados en la base de datos indicando si están activos y compatibles con el cultivo."""
    return mlServ.listar_modelosServ(
        id_cultivo=id_cultivo, db=db, current_user=current_user
    )


@router.get("/models/active", response_model=ModelInfo)
def modelo_activo(
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Obtiene los detalles del modelo de ML activo para el usuario actual y cultivo."""
    return mlServ.modelo_activoServ(
        id_cultivo=id_cultivo, db=db, current_user=current_user
    )


@router.post("/models/select/{id_modelo_ml}", response_model=ModelSelectionResponse)
def seleccionar_modelo(
    id_modelo_ml: int,
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Selecciona un modelo de ML por su ID y lo registra como activo para el usuario y cultivo."""
    return mlServ.seleccionar_modeloServ(
        id_modelo_ml=id_modelo_ml,
        id_cultivo=id_cultivo,
        db=db,
        current_user=current_user,
    )


@router.post("/prediccion")
def predecir_riego(
    data: PrediccionRiegoModel,
    id_cultivo: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return mlServ.predecir_riegoServ(
        data=data, id_cultivo=id_cultivo, db=db, current_user=current_user
    )


@router.post("/models/retrain")
def reentrenar_modelo_ia(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Encola una tarea en segundo plano para reentrenar el modelo Random Forest.
    """
    return mlServ.reentrenar_modelo_iaServ(
        background_tasks=background_tasks, db=db, current_user=current_user
    )


@router.post("/models/train-db")
def entrenar_desde_db(
    request: DbTrainingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Encola una tarea en segundo plano para entrenar un modelo a partir de los datos históricos de telemetría de la base de datos.
    Cada entrenamiento genera un nuevo registro persistido en la base de datos y un archivo de modelo físico único.
    """
    return mlServ.entrenar_desde_dbServ(
        request=request,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


@router.post("/predict-live/{id_cultivo}")
def ejecutar_prediccion_en_vivo(
    id_cultivo: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user_or_bff),
):
    return mlServ.ejecutar_prediccion_en_vivoServ(
        id_cultivo=id_cultivo, db=db, current_user=current_user
    )
