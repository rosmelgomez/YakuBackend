"""Selección del método de medición del actuador registrado."""


def measurement_method(assignment, source=None) -> str:
    device = getattr(assignment, "dispositivo", None)
    method = getattr(device, "metodo_medicion", None)
    if method in ("proximidad", "flujometro"):
        return method
    # Compatibilidad con inventario anterior a la clasificación de actuadores.
    if source is None:
        source = getattr(assignment, "fuente_agua", None)
        if source is None:
            source = getattr(getattr(assignment, "cultivo", None), "fuente_agua", None)
    from src.main.core.waterSource import normalize_source_type

    if source is None:
        raise ValueError("El actuador no tiene fuente ni método de medición configurados.")
    return "flujometro" if normalize_source_type(source.tipo) == "conexion_directa" else "proximidad"
