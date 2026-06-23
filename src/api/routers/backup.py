from datetime import datetime
from decimal import Decimal
import io
import os
import logging
import subprocess
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ...core.bff_auth import get_current_user_or_bff
from ...core.config import require_env

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/backup", tags=["Administración Backup"])


@router.get("")
def descargar_backup_db(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """
    Genera un backup en formato SQL de la base de datos y lo expone como descarga.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "YakuDB")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = require_env("DB_PASSWORD")

    # Intentar usar pg_dump ejecutable del sistema
    env = os.environ.copy()
    env["PGPASSWORD"] = db_password

    try:
        process = subprocess.run(
            ["pg_dump", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name],
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        sql_content = process.stdout
        return StreamingResponse(
            io.BytesIO(sql_content.encode("utf-8")),
            media_type="application/sql",
            headers={"Content-Disposition": "attachment; filename=yaku_backup.sql"}
        )
    except Exception as e:
        logger.info(f"[BACKUP WARNING] pg_dump falló o no está instalado ({e}). Usando fallback SQLAlchemy.")
        
        try:
            from sqlalchemy import MetaData
            from sqlalchemy.schema import CreateTable
            
            meta = MetaData()
            meta.reflect(bind=db.get_bind())
            
            sql_buffer = io.StringIO()
            sql_buffer.write("-- =========================================================\n")
            sql_buffer.write(f"-- YAKU DATABASE BACKUP (FALLBACK SQLALchemy)\n")
            sql_buffer.write(f"-- Fecha: {datetime.now().isoformat()}\n")
            sql_buffer.write("-- =========================================================\n\n")
            
            # 1. Definición de Tablas
            sql_buffer.write("-- Definición de Tablas\n")
            for table_name in meta.tables:
                table = meta.tables[table_name]
                sql_buffer.write(str(CreateTable(table).compile(db.get_bind())) + ";\n\n")
            
            # 2. Datos de Tablas
            sql_buffer.write("-- Datos de Tablas\n")
            for table_name in meta.tables:
                table = meta.tables[table_name]
                # Ejecutar consulta a la tabla
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
                        sql_buffer.write(f"INSERT INTO {table_name} ({cols}) VALUES ({vals});\n")
                    sql_buffer.write("\n")
            
            sql_content = sql_buffer.getvalue()
            return StreamingResponse(
                io.BytesIO(sql_content.encode("utf-8")),
                media_type="application/sql",
                headers={"Content-Disposition": "attachment; filename=yaku_backup_fallback.sql"}
            )
        except Exception as fallback_err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No fue posible generar la copia de seguridad"
            )
