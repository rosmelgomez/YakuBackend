"""Exportación de PostgreSQL mediante pg_dump o introspección SQLAlchemy."""

import io
import json
import logging
import os
import subprocess
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from src.main.core.yakuConfig import require_env

logger = logging.getLogger(__name__)


class BackupError(RuntimeError):
    """No fue posible exportar la base de datos."""


def _json_default(val):
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return str(val)


def exportarDatosUsuario(db: Session, id_usuario: int) -> tuple[str, str]:
    """Genera un respaldo acotado SOLO a los datos del usuario indicado (JSON),
    para administradores delegados vía HU-31 (permiso GESTIONAR_RESPALDOS)
    que no son administradores reales: nunca deben poder descargar el `pg_dump`
    completo de la base de datos, que incluye contraseñas hasheadas y datos
    de TODOS los usuarios.

    Recorre las tablas reflejadas y, para cada una, filtra por la columna que
    la vincula al usuario: `id_usuario` directamente, `id_asignacion` (a
    través de las asignaciones IoT del usuario) o `id_riego` (a través de sus
    sesiones de riego). Las tablas de catálogo (roles, tipos_metrica,
    permisos_catalogo, etc.) no tienen ninguna de esas columnas y quedan
    excluidas automáticamente. En `usuarios` solo se incluye la fila propia,
    sin el hash de la contraseña.
    """
    from sqlalchemy import MetaData

    meta = MetaData()
    meta.reflect(bind=db.get_bind())

    # IDs de asignaciones IoT propias, para las tablas que solo se vinculan
    # al usuario indirectamente a través de una asignación (telemetría, etc.)
    asignaciones_ids: list[int] = []
    if "asignaciones_iot" in meta.tables:
        asig_table = meta.tables["asignaciones_iot"]
        rows = db.execute(
            asig_table.select().where(asig_table.c.id_usuario == id_usuario)
        ).fetchall()
        asignaciones_ids = [r.id for r in rows]

    # IDs de sesiones de riego propias (para ejecuciones_riego, que solo
    # referencia id_riego, no id_asignacion ni id_usuario directamente)
    riego_ids: list[int] = []
    if "riego" in meta.tables and asignaciones_ids:
        riego_table = meta.tables["riego"]
        rows = db.execute(
            riego_table.select().where(riego_table.c.id_asignacion.in_(asignaciones_ids))
        ).fetchall()
        riego_ids = [r.id for r in rows]

    resultado: dict[str, list[dict]] = {}

    for table_name, table in meta.tables.items():
        columnas = table.columns.keys()

        if table_name == "usuarios":
            query = table.select().where(table.c.id == id_usuario)
        elif "id_usuario" in columnas:
            query = table.select().where(table.c.id_usuario == id_usuario)
        elif "id_asignacion" in columnas:
            if not asignaciones_ids:
                continue
            query = table.select().where(table.c.id_asignacion.in_(asignaciones_ids))
        elif table_name == "ejecuciones_riego" and "id_riego" in columnas:
            if not riego_ids:
                continue
            query = table.select().where(table.c.id_riego.in_(riego_ids))
        else:
            continue  # tabla de catálogo/sistema, no pertenece a un usuario en particular

        rows = db.execute(query).fetchall()
        if not rows:
            continue

        filas_dict = []
        for row in rows:
            fila = dict(row._mapping)
            if table_name == "usuarios":
                fila.pop("contrasena", None)
            filas_dict.append(fila)
        resultado[table_name] = filas_dict

    contenido = json.dumps(
        {
            "exportado_en": datetime.now().isoformat(),
            "id_usuario": id_usuario,
            "nota": "Respaldo acotado a los datos de este usuario (no incluye datos de otros usuarios ni credenciales).",
            "tablas": resultado,
        },
        default=_json_default,
        ensure_ascii=False,
        indent=2,
    )
    filename = f"yaku_mis_datos_usuario_{id_usuario}.json"
    return contenido, filename


def exportarBackup(db: Session):
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "YakuDB")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = require_env("DB_PASSWORD")
    env = os.environ.copy()
    env["PGPASSWORD"] = db_password
    try:
        process = subprocess.run(
            ["pg_dump", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        sql_content = process.stdout
        return (sql_content, "yaku_backup.sql")
    except Exception as e:
        logger.info(
            f"[BACKUP WARNING] pg_dump falló o no está instalado ({e}). Usando fallback SQLAlchemy."
        )
        try:
            from sqlalchemy import MetaData
            from sqlalchemy.schema import CreateTable

            meta = MetaData()
            meta.reflect(bind=db.get_bind())
            sql_buffer = io.StringIO()
            sql_buffer.write(
                "-- =========================================================\n"
            )
            sql_buffer.write(f"-- YAKU DATABASE BACKUP (FALLBACK SQLALchemy)\n")
            sql_buffer.write(f"-- Fecha: {datetime.now().isoformat()}\n")
            sql_buffer.write(
                "-- =========================================================\n\n"
            )
            sql_buffer.write("-- Definición de Tablas\n")
            for table_name in meta.tables:
                table = meta.tables[table_name]
                sql_buffer.write(
                    str(CreateTable(table).compile(db.get_bind())) + ";\n\n"
                )
            sql_buffer.write("-- Datos de Tablas\n")
            for table_name in meta.tables:
                table = meta.tables[table_name]
                rows = db.execute(table.select()).fetchall()
                if rows:
                    sql_buffer.write(f"-- Datos para la tabla: {table_name}\n")
                    for row in rows:
                        cols = ", ".join(table.columns.keys())
                        vals_list = []
                        for val in row:
                            if val is None:
                                vals_list.append("NULL")
                            elif isinstance(val, (int, float, Decimal)):
                                vals_list.append(str(val))
                            elif isinstance(val, bool):
                                vals_list.append("TRUE" if val else "FALSE")
                            else:
                                val_str = str(val).replace("'", "''")
                                vals_list.append(f"'{val_str}'")
                        vals = ", ".join(vals_list)
                        sql_buffer.write(
                            f"INSERT INTO {table_name} ({cols}) VALUES ({vals});\n"
                        )
                    sql_buffer.write("\n")
            sql_content = sql_buffer.getvalue()
            return (sql_content, "yaku_backup_fallback.sql")
        except Exception as fallback_err:
            raise BackupError(
                "No fue posible generar la copia de seguridad"
            ) from fallback_err
