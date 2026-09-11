"""Códigos de fuentes y adaptación al protocolo MQTT existente."""


def normalize_source_type(value: str) -> str:
    value = value.strip().lower()
    if value == "manguera":
        value = "conexion_directa"
    if value not in ("tanque", "conexion_directa"):
        raise ValueError("Tipo de fuente inválido: use tanque o conexion_directa.")
    return value


def source_firmware_config(source) -> dict:
    if source is None:
        return {"tipo_fuente": ""}
    kind = normalize_source_type(source.tipo)
    # Los actuadores instalados todavía identifican la conexión directa como manguera.
    result = {"tipo_fuente": "manguera" if kind == "conexion_directa" else kind}
    if kind == "conexion_directa":
        return result
    height = float(source.altura_tanque_cm)
    safety = float(source.altura_seguridad_cm) if source.altura_seguridad_cm is not None else 10.0
    if not 0 <= safety < height:
        raise ValueError("La altura de seguridad debe ser menor que la altura del tanque.")
    result.update(
        altura_total_cm=height,
        altura_seguridad_cm=safety,
        distancia_sin_agua_cm=height - safety,
        distancia_abrir_valvula_cm=height - safety,
        distancia_cerrar_valvula_cm=height * 0.10,
    )
    return result
