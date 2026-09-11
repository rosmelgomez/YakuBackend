from sqlalchemy.orm import Session

from src.main.model.models import usuarios


def queryActiveUserResultado(db: Session, user_id):
    return (
        db.query(usuarios)
        .filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True))
        .first()
    )
