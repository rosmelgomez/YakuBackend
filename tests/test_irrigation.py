import json

from src.services.irrigation import (
    DEFAULT_RELAY_MINUTES,
    MAX_RELAY_MINUTES,
    MIN_RELAY_MINUTES,
    build_relay_command,
    clamp_duration_seconds,
)


def test_relay_duration_is_clamped_to_safety_range():
    assert clamp_duration_seconds(None) == DEFAULT_RELAY_MINUTES * 60
    assert clamp_duration_seconds(1) == MIN_RELAY_MINUTES * 60
    assert clamp_duration_seconds(900) == 900
    assert clamp_duration_seconds(9999) == MAX_RELAY_MINUTES * 60


def test_on_command_carries_duration_and_off_does_not():
    on_payload = json.loads(build_relay_command("ON", 420))
    off_payload = json.loads(build_relay_command("OFF"))

    assert on_payload == {"accion": "ON", "duracion_seg": 420}
    assert off_payload == {"accion": "OFF"}


def test_firmware_has_local_timeout_and_accepts_timed_commands():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "esp32.ino").read_text(encoding="utf-8")
    assert 'commandDoc["duracion_seg"]' in source
    assert "DURACION_RELE_MAX_SEG = 1800" in source
    assert 'motivoBomba = "tiempo_maximo"' in source
    assert 'motivoValvula = "tiempo_maximo_valvula"' in source
