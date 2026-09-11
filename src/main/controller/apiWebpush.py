from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.webpushDto import SubscribeModel
from src.main.service import webpushServ

router = APIRouter(tags=["Web Push"])


@router.get("/webpush/public-key")
def get_public_key():
    return webpushServ.get_public_keyServ()


@router.get("/webpush/status")
def get_push_status(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return webpushServ.get_push_statusServ(db=db, current_user=current_user)


@router.post("/webpush/subscribe")
def subscribe_user(
    data: SubscribeModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return webpushServ.subscribe_userServ(data=data, db=db, current_user=current_user)
