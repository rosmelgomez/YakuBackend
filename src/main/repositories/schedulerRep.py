from sqlalchemy.orm import Session

from src.main.model.models import asignaciones_iot, riego



def queryCheckDurationsActiveSessions(db: Session):
    return (
        db.query(riego)
        .filter(
            riego.estado == False,
            riego.motivo_cierre.is_(None) | ~riego.motivo_cierre.like("pausado_%"),
        )
        .all()
    )


def queryCheckDurationsAsig(db: Session, session: Session):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == session.id_asignacion)
        .first()
    )
