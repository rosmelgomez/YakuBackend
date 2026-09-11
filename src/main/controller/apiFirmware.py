from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.firmwareDto import (
    FirmwareInstallationCreate,
    FirmwareInstallationResponse,
    FirmwareInstallationUpdate,
    FirmwareVersionResponse,
)
from src.main.service import firmwareServ

router = APIRouter(prefix="/firmware", tags=["Firmware"])


@router.get("/versions", response_model=list[FirmwareVersionResponse])
def list_versions(
    include_discontinued: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return firmwareServ.list_versionsServ(
        include_discontinued=include_discontinued, db=db, current_user=current_user
    )


@router.post(
    "/versions",
    response_model=FirmwareVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    metadata: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return await firmwareServ.create_versionServ(
        metadata=metadata, files=files, db=db, current_user=current_user
    )


@router.get("/versions/{version_id}/files/{filename}")
def download_segment(
    version_id: int,
    filename: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return firmwareServ.download_segmentServ(
        version_id=version_id, filename=filename, db=db, current_user=current_user
    )


@router.patch(
    "/versions/{version_id}/discontinue", response_model=FirmwareVersionResponse
)
def discontinue_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return firmwareServ.discontinue_versionServ(
        version_id=version_id, db=db, current_user=current_user
    )


@router.post("/devices/{device_id}/provisioning")
def get_provisioning(
    device_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return firmwareServ.get_provisioningServ(
        device_id=device_id, db=db, current_user=current_user
    )


@router.post(
    "/installations",
    response_model=FirmwareInstallationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_installation(
    payload: FirmwareInstallationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return firmwareServ.create_installationServ(
        payload=payload, db=db, current_user=current_user
    )


@router.patch(
    "/installations/{installation_id}", response_model=FirmwareInstallationResponse
)
def update_installation(
    installation_id: int,
    payload: FirmwareInstallationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return firmwareServ.update_installationServ(
        installation_id=installation_id,
        payload=payload,
        db=db,
        current_user=current_user,
    )


@router.get("/installations", response_model=list[FirmwareInstallationResponse])
def list_installations(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return firmwareServ.list_installationsServ(
        limit=limit, db=db, current_user=current_user
    )
