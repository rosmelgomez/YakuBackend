"""Asignación de permisos granulares a usuarios, adicionales al rol binario (HU-31).

El rol de administrador (id_rol=1) sigue teniendo acceso total a todo, tal como
antes. Estos permisos sirven para otorgarle a un usuario "agricultor" (id_rol=2)
capacidades administrativas puntuales SIN volverlo administrador completo.

Deliberadamente el catálogo se limita a acciones de solo lectura o que no
alteran el funcionamiento del sistema (generar un respaldo, consultar la
auditoría). No se ofrecen permisos que permitan modificar dispositivos,
usuarios, horarios de riego o la configuración del broker MQTT: esas acciones
quedan reservadas exclusivamente al rol de administrador.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.model.models import logs_sistema, permisos_catalogo, usuario_permisos, usuarios
from src.main.repositories import sessionRep as session_repository

CATALOGO_PERMISOS = (
    ("GESTIONAR_RESPALDOS", "Generar respaldos", "Descargar copias de seguridad de la base de datos (no permite restaurar ni modificar datos)."),
    ("VER_AUDITORIA", "Ver auditoría del sistema", "Consultar el historial de mantenimiento y auditoría (solo lectura)."),
)


def _require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede asignar permisos.",
        )


def listar_catalogo_permisosServ(db: Session = None, current_user=None):
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador.",
        )
    return db.query(permisos_catalogo).order_by(permisos_catalogo.nombre.asc()).all()


def listar_permisos_usuarioServ(
    id_usuario: int, db: Session = None, current_user=None
):
    if current_user.id_rol != 1 and current_user.id_usuario != id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para consultar los permisos de este usuario.",
        )
    asignados = (
        db.query(permisos_catalogo)
        .join(usuario_permisos, usuario_permisos.id_permiso == permisos_catalogo.id)
        .filter(usuario_permisos.id_usuario == id_usuario)
        .all()
    )
    return asignados


def asignar_permisos_usuarioServ(
    id_usuario: int,
    codigos: list[str],
    db: Session = None,
    current_user=None,
):
    """Reemplaza el conjunto de permisos granulares otorgados a un usuario."""
    _require_admin(current_user)

    user = db.query(usuarios).filter(usuarios.id_usuario == id_usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    codigos_validos = {c for c, _, _ in CATALOGO_PERMISOS}
    invalidos = set(codigos) - codigos_validos
    if invalidos:
        raise HTTPException(
            status_code=400, detail=f"Códigos de permiso inválidos: {sorted(invalidos)}"
        )

    permisos_db = (
        db.query(permisos_catalogo).filter(permisos_catalogo.codigo.in_(codigos)).all()
        if codigos
        else []
    )

    db.query(usuario_permisos).filter(usuario_permisos.id_usuario == id_usuario).delete()

    for permiso in permisos_db:
        session_repository.add(
            db,
            usuario_permisos(
                id_usuario=id_usuario,
                id_permiso=permiso.id,
                otorgado_por=current_user.id_usuario,
            ),
        )

    session_repository.add(
        db,
        logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="asignar_permisos",
            modulo="Permisos",
            descripcion=(
                f"Permisos de {user.correo} actualizados por {current_user.correo}: "
                f"{', '.join(sorted(codigos)) if codigos else '(ninguno)'}."
            ),
        ),
    )
    session_repository.commit(db)

    return listar_permisos_usuarioServ(id_usuario, db=db, current_user=current_user)


def usuario_tiene_permiso(db: Session, current_user, codigo: str) -> bool:
    """Helper de autorización: el administrador siempre tiene todos los
    permisos; para otros usuarios se verifica el permiso granular otorgado."""
    if current_user is None:
        return False
    if current_user.id_rol == 1:
        return True
    existe = (
        db.query(usuario_permisos)
        .join(permisos_catalogo, permisos_catalogo.id == usuario_permisos.id_permiso)
        .filter(
            usuario_permisos.id_usuario == current_user.id_usuario,
            permisos_catalogo.codigo == codigo,
        )
        .first()
    )
    return existe is not None


def require_permiso(db: Session, current_user, codigo: str) -> None:
    if not usuario_tiene_permiso(db, current_user, codigo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes el permiso necesario para realizar esta acción.",
        )
