from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.dispositivoDto import (
    AsignarComponentePayload,
    ComponenteCreate,
    ComponenteResponseModel,
    DispositivoAdminResponse,
    DispositivoConfigResponseModel,
    DispositivoConSensoresResponseModel,
    DispositivoCreate,
    DispositivoResponseModel,
    TipoComponenteResponseModel,
    TipoDispositivoResponseModel,
    TipoMetricaResponseModel,
)
from src.main.service import dispositivoServ

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])

legacy_router = APIRouter(prefix="/bomba", tags=["Legacy Bomba"])

singular_router = APIRouter(prefix="/dispositivo", tags=["Dispositivo Singular"])


@router.get("", response_model=List[DispositivoAdminResponse])
def listar_dispositivos(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Lista los dispositivos del sistema.
    """
    return dispositivoServ.listar_dispositivosServ(
        id_usuario=id_usuario, db=db, current_user=current_user
    )


@router.get("/me", response_model=List[DispositivoResponseModel])
def listar_mis_dispositivos(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """
    Retorna la lista de dispositivos asignados únicamente al usuario autenticado actual.
    """
    return dispositivoServ.listar_mis_dispositivosServ(db=db, current_user=current_user)


@router.get("/tipos", response_model=List[TipoDispositivoResponseModel])
def listar_tipos_dispositivo(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los tipos de dispositivos disponibles."""
    return dispositivoServ.listar_tipos_dispositivoServ(
        db=db, current_user=current_user
    )


@router.get("/metricas", response_model=List[TipoMetricaResponseModel])
def listar_tipos_metrica(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los tipos de métricas disponibles."""
    return dispositivoServ.listar_tipos_metricaServ(db=db, current_user=current_user)


@router.get("/componentes/tipos", response_model=List[TipoComponenteResponseModel])
def listar_tipos_componente(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los tipos de componentes disponibles en el catálogo."""
    return dispositivoServ.listar_tipos_componenteServ(db=db, current_user=current_user)


@router.get("/componentes", response_model=List[ComponenteResponseModel])
def listar_componentes(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Lista todos los componentes físicos registrados en el inventario."""
    return dispositivoServ.listar_componentesServ(db=db, current_user=current_user)


@router.get("/siguiente-client-id")
def obtener_siguiente_client_id(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """
    Calcula el siguiente Client ID MQTT consultando en la base de datos.
    Solo administradores.
    """
    return dispositivoServ.obtener_siguiente_client_idServ(
        db=db, current_user=current_user
    )


@router.post("/activar/{dispositivo_id}")
def activar_dispositivo(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.activar_dispositivoServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


@router.post("/desactivar/{dispositivo_id}")
def desactivar_dispositivo(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.desactivar_dispositivoServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


@router.post("/funcionamiento/{dispositivo_id}/{estado}")
def establecer_funcionamiento_dispositivo(
    dispositivo_id: int,
    estado: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.establecer_funcionamiento_dispositivoServ(
        dispositivo_id=dispositivo_id, estado=estado, db=db, current_user=current_user
    )


@legacy_router.post("/activar/{dispositivo_id}")
def activar_bomba_legacy(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.activar_bomba_legacyServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


@legacy_router.post("/desactivar/{dispositivo_id}")
def desactivar_bomba_legacy(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.desactivar_bomba_legacyServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


@legacy_router.post("/funcionamiento/{dispositivo_id}")
def establecer_funcionamiento_dispositivo_legacy(
    dispositivo_id: int,
    activo: bool | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.establecer_funcionamiento_dispositivo_legacyServ(
        dispositivo_id=dispositivo_id, activo=activo, db=db, current_user=current_user
    )


@legacy_router.get("/dispositivos", response_model=List[DispositivoResponseModel])
def listar_dispositivos_legacy(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.listar_dispositivos_legacyServ(
        id_usuario=id_usuario, db=db, current_user=current_user
    )


@router.get(
    "/usuario/{id_user}", response_model=List[DispositivoConSensoresResponseModel]
)
def listar_dispositivos_de_usuario(
    id_user: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Lista todos los dispositivos asociados a un usuario específico (id_user),
    incluyendo la información de los sensores de cada dispositivo.
    Solo accesible por administradores (id_rol = 1).
    """
    return dispositivoServ.listar_dispositivos_de_usuarioServ(
        id_user=id_user, db=db, current_user=current_user
    )


@router.get(
    "/usuario/config/{id_user}", response_model=List[DispositivoConfigResponseModel]
)
def obtener_config_dispositivos_usuario(
    id_user: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Retorna datos esenciales para la configuración de los archivos .ino de cada dispositivo de un usuario.
    Solo accesible por administradores (id_rol = 1).
    """
    return dispositivoServ.obtener_config_dispositivos_usuarioServ(
        id_user=id_user, db=db, current_user=current_user
    )


@router.get("/admin/stock", response_model=List[DispositivoResponseModel])
def listar_stock_disponibles(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """
    Lista todos los dispositivos que están disponibles en el almacén (estado = 'disponible').
    Solo accesible por administradores (id_rol = 1).
    """
    return dispositivoServ.listar_stock_disponiblesServ(
        db=db, current_user=current_user
    )


@router.post("/admin/asignar/{dispositivo_id}/{id_usuario}/{id_cultivo}")
def asignar_dispositivo_a_cultivo(
    dispositivo_id: int,
    id_usuario: int,
    id_cultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Asigna un dispositivo disponible en stock a un agricultor y cultivo específico.
    El dispositivo cambia su estado a 'asignado' y se crean las asignaciones inactivas por defecto.
    Solo accesible por administradores (id_rol = 1).
    """
    return dispositivoServ.asignar_dispositivo_a_cultivoServ(
        dispositivo_id=dispositivo_id,
        id_usuario=id_usuario,
        id_cultivo=id_cultivo,
        db=db,
        current_user=current_user,
    )


@router.post("/admin/liberar/{dispositivo_id}")
def liberar_dispositivo_a_stock(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Desvincula un dispositivo del agricultor/cultivo y lo regresa al stock disponible.
    Desactiva (o elimina) todas sus asignaciones activas e inhabilita su telemetría.
    Solo accesible por administradores (id_rol = 1).
    """
    return dispositivoServ.liberar_dispositivo_a_stockServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


@router.post("/calibrar/{dispositivo_id}/{pin_gpio}/{offset}")
def calibrar_sensor_remoto(
    dispositivo_id: int,
    pin_gpio: int,
    offset: float,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Permite calibrar un sensor físicamente compensando las lecturas (offset)
    y enviando la instrucción vía MQTT al microcontrolador.
    """
    return dispositivoServ.calibrar_sensor_remotoServ(
        dispositivo_id=dispositivo_id,
        pin_gpio=pin_gpio,
        offset=offset,
        db=db,
        current_user=current_user,
    )


@router.post(
    "", response_model=DispositivoResponseModel, status_code=status.HTTP_201_CREATED
)
def registrar_dispositivo(
    payload: DispositivoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra un nuevo dispositivo en el inventario. Solo administradores."""
    return dispositivoServ.registrar_dispositivoServ(
        payload=payload, db=db, current_user=current_user
    )


@router.post(
    "/componentes",
    response_model=ComponenteResponseModel,
    status_code=status.HTTP_201_CREATED,
)
def registrar_componente(
    payload: ComponenteCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra un nuevo componente físico en stock. Solo administradores."""
    return dispositivoServ.registrar_componenteServ(
        payload=payload, db=db, current_user=current_user
    )


@router.post("/admin/dispositivo/{dispositivo_id}/estado/{nuevo_estado}")
def cambiar_estado_dispositivo_stock(
    dispositivo_id: int,
    nuevo_estado: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Cambia el estado de un dispositivo en stock (Retirado, reparacion, disponible).
    """
    return dispositivoServ.cambiar_estado_dispositivo_stockServ(
        dispositivo_id=dispositivo_id,
        nuevo_estado=nuevo_estado,
        db=db,
        current_user=current_user,
    )


@router.post("/admin/componente/{componente_id}/estado/{nuevo_estado}")
def cambiar_estado_componente_stock(
    componente_id: int,
    nuevo_estado: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Cambia el estado de un componente en stock (Retirado, reparacion, disponible).
    """
    return dispositivoServ.cambiar_estado_componente_stockServ(
        componente_id=componente_id,
        nuevo_estado=nuevo_estado,
        db=db,
        current_user=current_user,
    )


@router.post("/admin/asignar-componente")
def asignar_componente_dispositivo(
    payload: AsignarComponentePayload,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Vincula un componente en stock a un dispositivo asignado en campo.
    El componente sale del almacén (id_almacen = None) y se crea un registro en asignaciones_iot.
    Si el componente es de categoría 'actuador', se registra una configuracion_tanque vacía.
    Solo accesible por administradores (id_rol = 1).
    """
    return dispositivoServ.asignar_componente_dispositivoServ(
        payload=payload, db=db, current_user=current_user
    )


@router.post("/admin/liberar-componente/{componente_id}")
def liberar_componente_dispositivo(
    componente_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Desvincula un componente de su dispositivo y lo regresa al stock disponible.
    Desactiva las asignaciones activas asociadas a este componente.
    Solo accesible por administradores (id_rol = 1).
    """
    return dispositivoServ.liberar_componente_dispositivoServ(
        componente_id=componente_id, db=db, current_user=current_user
    )


@router.get("/{dispositivo_id}", response_model=DispositivoResponseModel)
def obtener_detalle_dispositivo(
    dispositivo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Obtiene los detalles de un dispositivo por su ID.
    """
    return dispositivoServ.obtener_detalle_dispositivoServ(
        dispositivo_id=dispositivo_id, db=db, current_user=current_user
    )


@router.post("/{dispositivo_id}/{active}")
def activar_desactivar_dispositivo_plural(
    dispositivo_id: int,
    active: bool,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.activar_desactivar_dispositivo_pluralServ(
        dispositivo_id=dispositivo_id, active=active, db=db, current_user=current_user
    )


@singular_router.post("/{dispositivo_id}/{active}")
def activar_desactivar_dispositivo_singular(
    dispositivo_id: int,
    active: bool,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dispositivoServ.activar_desactivar_dispositivo_singularServ(
        dispositivo_id=dispositivo_id, active=active, db=db, current_user=current_user
    )
