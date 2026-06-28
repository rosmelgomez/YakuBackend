import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.bff_auth import get_current_user_or_bff
from ...db.models import (
    asignaciones_iot,
    cultivos,
    dispositivos,
    fuentes_agua,
    instalaciones_firmware,
    usuarios,
    versiones_firmware,
)
from ...schemas.firmware import (
    FirmwareInstallationCreate,
    FirmwareInstallationResponse,
    FirmwareInstallationUpdate,
    FirmwareVersionResponse,
)
from ..dependencies import get_db


router = APIRouter(prefix="/firmware", tags=["Firmware"])
ROOT_DIR = Path(__file__).resolve().parents[3]

env_storage_path = os.getenv("FIRMWARE_STORAGE_PATH", "firmware_store")
if Path(env_storage_path).is_absolute():
    FIRMWARE_DIR = Path(env_storage_path).resolve()
else:
    FIRMWARE_DIR = (ROOT_DIR / env_storage_path).resolve()

MAX_SEGMENT_SIZE = 8 * 1024 * 1024
ALLOWED_CHIPS = {"ESP32", "ESP32-S3"}
ALLOWED_DEVICE_TYPES = {"sensores", "riego"}


def get_version_dir(version: versiones_firmware) -> Path:
    if version.ubicacion_archivo:
        path = Path(version.ubicacion_archivo)
        if path.is_absolute():
            if path.exists():
                return path
        else:
            root_resolved = (ROOT_DIR / path).resolve()
            if root_resolved.is_dir():
                return root_resolved
            firmware_resolved = (FIRMWARE_DIR / path).resolve()
            if firmware_resolved.is_dir():
                return firmware_resolved
    return (FIRMWARE_DIR / version.directorio).resolve()



def require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para administradores")


def public_version(version: versiones_firmware) -> dict:
    release_dir = get_version_dir(version)
    missing_files = []
    for item in version.manifiesto.get("segmentos", []):
        name = Path(str(item.get("nombre", ""))).name
        if name and not (release_dir / name).is_file():
            missing_files.append(name)
    return {
        "id": version.id,
        "version": version.version,
        "chip": version.chip,
        "tipo_dispositivo": version.tipo_dispositivo,
        "descripcion": version.descripcion,
        "publicado": version.publicado,
        "descontinuado": version.descontinuado,
        "ubicacion_archivo": version.ubicacion_archivo,
        "manifiesto": version.manifiesto,
        "archivos_faltantes": missing_files,
        "fecha_registro": version.fecha_registro,
        "fecha_descontinuado": version.fecha_descontinuado,
    }


def build_assignment_metric_map(assignments: list[asignaciones_iot], device: dispositivos) -> tuple[dict[str, int], list[dict]]:
    metric_map = {}
    assignment_detail = []
    fallback_assignment_id = None
    device_type_name = (device.tipo.nombre if device.tipo else "").lower()
    is_water_controller = any(
        word in device_type_name
        for word in ("actuador", "nivel", "riego", "tanque")
    )

    for assignment in assignments:
        code = assignment.tipo_metrica.codigo if assignment.tipo_metrica else None
        if not code and assignment.componente and assignment.componente.modelo:
            category = assignment.componente.modelo.categoria.upper()
            pin_suffix = f"_GPIO{assignment.pin_gpio}" if assignment.pin_gpio is not None else ""
            code = f"{category}{pin_suffix}"
            if category == "ACTUADOR":
                is_water_controller = True
            if fallback_assignment_id is None and category == "ACTUADOR":
                fallback_assignment_id = assignment.id
        if fallback_assignment_id is None and is_water_controller:
            fallback_assignment_id = assignment.id
        if code:
            metric_map[code] = assignment.id
        assignment_detail.append({
            "id_asignacion": assignment.id,
            "codigo_metrica": code,
            "pin_gpio": assignment.pin_gpio,
            "id_componente": assignment.id_componente,
        })

    if is_water_controller and "NIVEL_AGUA" not in metric_map and fallback_assignment_id is not None:
        metric_map["NIVEL_AGUA"] = fallback_assignment_id

    return metric_map, assignment_detail


def build_tank_config(assignments: list[asignaciones_iot], db: Session) -> dict[str, float]:
    source = None
    for assignment in assignments:
        if assignment.fuente_agua is not None:
            source = assignment.fuente_agua
            break
    if source is None:
        source_id = next((item.id_fuente_agua for item in assignments if item.id_fuente_agua is not None), None)
        if source_id is None:
            source_id = next(
                (
                    item.cultivo.id_fuente_agua
                    for item in assignments
                    if item.cultivo is not None and item.cultivo.id_fuente_agua is not None
                ),
                None,
            )
        if source_id is not None:
            source = db.query(fuentes_agua).filter(fuentes_agua.id == source_id).first()
    altura_total_cm = float(source.altura_tanque_cm or 50.0) if source else 50.0
    distancia_seguridad_cm = float(source.altura_seguridad_cm or 10.0) if source else 10.0
    distancia_sin_agua_cm = max(0.0, altura_total_cm - distancia_seguridad_cm)
    return {
        "altura_total_cm": altura_total_cm,
        "altura_seguridad_cm": distancia_seguridad_cm,
        "distancia_sin_agua_cm": distancia_sin_agua_cm,
        "distancia_abrir_valvula_cm": distancia_sin_agua_cm,
        "distancia_cerrar_valvula_cm": max(0.0, altura_total_cm * 0.10),
    }


def firmware_sort_key() -> tuple:
    return (
        versiones_firmware.fecha_registro.desc(),
        versiones_firmware.id.desc(),
    )


@router.get("/versions", response_model=list[FirmwareVersionResponse])
def list_versions(
    include_discontinued: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    query = db.query(versiones_firmware)
    if not include_discontinued:
        query = query.filter(versiones_firmware.descontinuado == False)
    versions = query.order_by(*firmware_sort_key()).all()
    return [public_version(item) for item in versions]


@router.post("/versions", response_model=FirmwareVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    metadata: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    try:
        payload = json.loads(metadata)
        version = str(payload["version"]).strip()
        chip = str(payload["chip"]).strip().upper()
        device_type = str(payload["tipo_dispositivo"]).strip().lower()
        segments = payload["segmentos"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Metadatos de firmware invalidos") from exc

    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise HTTPException(status_code=422, detail="La version debe usar formato semantico, por ejemplo 1.2.0")
    if chip not in ALLOWED_CHIPS or device_type not in ALLOWED_DEVICE_TYPES:
        raise HTTPException(status_code=422, detail="Chip o tipo de dispositivo no compatible")
    if not isinstance(segments, list) or not segments or len(segments) > 5:
        raise HTTPException(status_code=422, detail="Se requieren entre 1 y 5 segmentos")

    uploads = {Path(item.filename or "").name: item for item in files}
    requested_names = [Path(str(item.get("nombre", ""))).name for item in segments]
    if len(set(requested_names)) != len(requested_names) or set(uploads) != set(requested_names):
        raise HTTPException(status_code=422, detail="Los archivos no coinciden con el manifiesto")

    release_key = uuid.uuid4().hex
    release_dir = (FIRMWARE_DIR / release_key).resolve()
    if FIRMWARE_DIR not in release_dir.parents:
        raise HTTPException(status_code=400, detail="Ruta de firmware invalida")
    release_dir.mkdir(parents=True, exist_ok=False)

    manifest_segments = []
    try:
        for segment in segments:
            name = Path(str(segment["nombre"])).name
            raw_address = segment["direccion"]
            address = int(raw_address, 0) if isinstance(raw_address, str) else int(raw_address)
            if address < 0 or not name.lower().endswith(".bin"):
                raise ValueError("Segmento invalido")

            content = await uploads[name].read(MAX_SEGMENT_SIZE + 1)
            if not content or len(content) > MAX_SEGMENT_SIZE:
                raise HTTPException(status_code=413, detail=f"El segmento {name} excede el limite de 8 MB")
            destination = release_dir / name
            destination.write_bytes(content)
            manifest_segments.append({
                "nombre": name,
                "direccion": address,
                "sha256": hashlib.sha256(content).hexdigest(),
                "tamano": len(content),
            })

        manifest = {
            "schema_version": 1,
            "version": version,
            "chip": chip,
            "tipo_dispositivo": device_type,
            "segmentos": manifest_segments,
        }
        relative_release_dir = Path(release_dir).relative_to(ROOT_DIR).as_posix()
        record = versiones_firmware(
            version=version,
            chip=chip,
            tipo_dispositivo=device_type,
            descripcion=str(payload.get("descripcion") or "").strip() or None,
            manifiesto=manifest,
            directorio=release_key,
            ubicacion_archivo=relative_release_dir,
            publicado=bool(payload.get("publicado", True)),
            creado_por=current_user.id_usuario,
        )
        now = datetime.now()
        previous_versions = db.query(versiones_firmware).filter(
            versiones_firmware.chip == chip,
            versiones_firmware.tipo_dispositivo == device_type,
            versiones_firmware.descontinuado == False,
        ).all()
        for previous in previous_versions:
            previous.publicado = False
            previous.descontinuado = True
            previous.fecha_descontinuado = now
            db.add(previous)
        db.add(record)
        db.commit()
        db.refresh(record)
        return public_version(record)
    except HTTPException:
        db.rollback()
        shutil.rmtree(release_dir, ignore_errors=True)
        raise
    except (IntegrityError, KeyError, TypeError, ValueError) as exc:
        db.rollback()
        shutil.rmtree(release_dir, ignore_errors=True)
        detail = "La version ya existe" if isinstance(exc, IntegrityError) else "Manifiesto de segmentos invalido"
        raise HTTPException(status_code=409 if isinstance(exc, IntegrityError) else 422, detail=detail) from exc


@router.get("/versions/{version_id}/files/{filename}")
def download_segment(
    version_id: int,
    filename: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    version = db.query(versiones_firmware).filter(versiones_firmware.id == version_id).first()
    if not version or not version.publicado or version.descontinuado:
        raise HTTPException(status_code=404, detail="Firmware no encontrado")
    safe_name = Path(filename).name
    allowed = {item["nombre"] for item in version.manifiesto.get("segmentos", [])}
    if safe_name not in allowed:
        raise HTTPException(status_code=404, detail="Segmento no encontrado")
    release_dir = get_version_dir(version).resolve()
    path = (release_dir / safe_name).resolve()
    if release_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Archivo de firmware no encontrado")
    return FileResponse(path, media_type="application/octet-stream", filename=safe_name)


@router.patch("/versions/{version_id}/discontinue", response_model=FirmwareVersionResponse)
def discontinue_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    version = db.query(versiones_firmware).filter(versiones_firmware.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Firmware no encontrado")
    version.descontinuado = True
    version.publicado = False
    version.fecha_descontinuado = datetime.now()
    db.add(version)
    db.commit()
    db.refresh(version)
    return public_version(version)


@router.post("/devices/{device_id}/provisioning")
def get_provisioning(
    device_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    device = db.query(dispositivos).filter(dispositivos.id_dispositivo == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    assignments = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_dispositivo == device_id,
    ).all()
    if not assignments:
        raise HTTPException(status_code=409, detail="El dispositivo no tiene asignaciones registradas")

    user_ids = {item.id_usuario for item in assignments}
    crop_ids = {item.id_cultivo for item in assignments if item.id_cultivo is not None}
    if len(user_ids) != 1 or len(crop_ids) != 1:
        raise HTTPException(status_code=409, detail="Las asignaciones deben pertenecer a un agricultor y cultivo unicos")
    user_id = next(iter(user_ids))
    crop_id = next(iter(crop_ids))
    farmer = db.query(usuarios).filter(usuarios.id_usuario == user_id).first()
    crop = db.query(cultivos).filter(cultivos.id_cultivo == crop_id).first()

    metric_map, assignment_detail = build_assignment_metric_map(assignments, device)
    tank_config = build_tank_config(assignments, db)

    compact_mac = re.sub(r"[^0-9A-F]", "", (device.mac_address or "").upper())
    device_uid = device.client_id_mqtt or (f"YAKU-{compact_mac}" if compact_mac else f"YAKU-DEVICE-{device_id}")
    if not device.client_id_mqtt:
        device.client_id_mqtt = device_uid
    if not device.topic_pub:
        device.topic_pub = "yaku/riego/datos" if "NIVEL_AGUA" not in metric_map else "yaku/tanque/datos"
    if not device.topic_sub:
        device.topic_sub = "yaku/riego/comando"
    db.commit()
    return {
        "schema_version": 1,
        "device_uid": device_uid,
        "id_dispositivo": device_id,
        "id_usuario": user_id,
        "agricultor": f"{farmer.nombre} {farmer.apellido or ''}".strip() if farmer else None,
        "id_cultivo": crop_id,
        "cultivo": crop.nombre_planta if crop else None,
        "asignaciones": metric_map,
        "detalle_asignaciones": assignment_detail,
        "tanque": tank_config,
        **tank_config,
        "captura_segundos": 60,
        "cooldown_riego_minutos": 60,
        "mqtt": {
            "host": os.getenv("MQTT_HOST", ""),
            "port": int(os.getenv("MQTT_PORT", "8883")),
            "client_id": device_uid,
            "topic_pub": device.topic_pub,
            "topic_sub": device.topic_sub,
            "tls": os.getenv("MQTT_TLS_ENABLED", "true").lower() in {"1", "true", "yes"},
        },
    }


@router.post("/installations", response_model=FirmwareInstallationResponse, status_code=status.HTTP_201_CREATED)
def create_installation(
    payload: FirmwareInstallationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    firmware = db.query(versiones_firmware).filter(versiones_firmware.id == payload.id_firmware).first()
    device = db.query(dispositivos).filter(dispositivos.id_dispositivo == payload.id_dispositivo).first()
    if not firmware or not firmware.publicado or firmware.descontinuado or not device:
        raise HTTPException(status_code=404, detail="Firmware o dispositivo no encontrado")
    record = instalaciones_firmware(
        id_firmware=payload.id_firmware,
        id_dispositivo=payload.id_dispositivo,
        id_administrador=current_user.id_usuario,
        chip_detectado=payload.chip_detectado,
        mac_detectada=payload.mac_detectada,
        estado="iniciada",
        progreso=0,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/installations/{installation_id}", response_model=FirmwareInstallationResponse)
def update_installation(
    installation_id: int,
    payload: FirmwareInstallationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    record = db.query(instalaciones_firmware).filter(instalaciones_firmware.id == installation_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Instalacion no encontrada")
    record.estado = payload.estado
    record.progreso = payload.progreso
    record.mensaje = payload.mensaje
    if payload.estado in {"completada", "error", "cancelada"}:
        record.fecha_fin = datetime.now()
    if payload.estado == "completada":
        firmware = db.query(versiones_firmware).filter(versiones_firmware.id == record.id_firmware).first()
        device = db.query(dispositivos).filter(dispositivos.id_dispositivo == record.id_dispositivo).first()
        if firmware and device:
            device.firmware_version = firmware.version
            if record.mac_detectada and not device.mac_address:
                device.mac_address = record.mac_detectada
    db.commit()
    db.refresh(record)
    return record


@router.get("/installations", response_model=list[FirmwareInstallationResponse])
def list_installations(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_admin(current_user)
    safe_limit = min(max(limit, 1), 100)
    return db.query(instalaciones_firmware).order_by(instalaciones_firmware.fecha_inicio.desc()).limit(safe_limit).all()


def sincronizar_firmwares_disco(db: Session) -> None:
    """
    Sincroniza los metadatos (tamaño y hash SHA256) de los segmentos de firmware 
    guardados en la base de datos con los archivos reales presentes en el disco.
    Esto permite que al desplegar en producción/nube, si hay cambios en los archivos 
    .bin, la base de datos se actualice automáticamente al arrancar.
    """
    import os
    import hashlib
    from sqlalchemy.orm.attributes import flag_modified

    logger.info("Iniciando sincronización automática de firmwares en disco...")
    versions = db.query(versiones_firmware).all()
    
    for v in versions:
        try:
            dir_path = get_version_dir(v)
        except Exception:
            dir_path = ROOT_DIR / "firmware_store" / (v.directorio or "")
            
        if not dir_path.exists():
            logger.warning(f"Directorio de firmware no encontrado: {dir_path}")
            continue
            
        manifest = v.manifiesto
        if not manifest or "segmentos" not in manifest:
            continue
            
        updated = False
        for segment in manifest["segmentos"]:
            name = segment.get("nombre")
            if not name:
                continue
            
            file_path = dir_path / name
            if not file_path.exists():
                alt_name = name.replace("-", "_") if "-" in name else name.replace("_", "-")
                file_path = dir_path / alt_name
                
            if not file_path.exists():
                logger.warning(f"Segmento de firmware {name} no encontrado en {dir_path}")
                continue
                
            try:
                content = file_path.read_bytes()
                new_size = len(content)
                new_hash = hashlib.sha256(content).hexdigest()
                
                if segment.get("tamano") != new_size or segment.get("sha256") != new_hash:
                    logger.info(f"Sincronizando segmento {name} para versión {v.version} ({v.chip}): {segment.get('tamano')} -> {new_size} bytes")
                    segment["tamano"] = new_size
                    segment["sha256"] = new_hash
                    updated = True
            except Exception as e:
                logger.error(f"Error al calcular hash de {file_path}: {e}")
                
        if updated:
            v.manifiesto = manifest
            flag_modified(v, 'manifiesto')
            try:
                db.commit()
                logger.info(f"Base de datos actualizada con éxito para la versión {v.version} ({v.chip})")
            except Exception as e:
                db.rollback()
                logger.error(f"Error al guardar actualización de firmware {v.version}: {e}")
                
    logger.info("Sincronización de firmwares completada.")
