"""Operaciones de persistencia compartidas; el servicio decide la transacción."""

from sqlalchemy.orm import Session


def add(db: Session, *args, **kwargs):
    return db.add(*args, **kwargs)


def add_all(db: Session, *args, **kwargs):
    return db.add_all(*args, **kwargs)


def commit(db: Session, *args, **kwargs):
    return db.commit(*args, **kwargs)


def delete(db: Session, *args, **kwargs):
    return db.delete(*args, **kwargs)


def flush(db: Session, *args, **kwargs):
    return db.flush(*args, **kwargs)


def refresh(db: Session, *args, **kwargs):
    return db.refresh(*args, **kwargs)


def rollback(db: Session, *args, **kwargs):
    return db.rollback(*args, **kwargs)
