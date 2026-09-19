"""Script manual de respaldo: ahora bootstrapServ.initialize_backend() ya
ejecuta estos mismos indices automaticamente en cada arranque via
bootstrapRep.ensure_performance_indexes(). Este script queda por si se
necesita aplicarlos a mano contra una base de datos sin reiniciar la app."""

import logging

from src.main.repositories.bootstrapRep import ensure_performance_indexes

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    ensure_performance_indexes()
