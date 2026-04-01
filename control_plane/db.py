from __future__ import annotations

from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from control_plane.runtime import ensure_runtime_dirs, get_db_path


_engine = None
_engine_path = None


def get_engine():
    global _engine, _engine_path
    ensure_runtime_dirs()
    current_path = get_db_path()
    if _engine is None or _engine_path != current_path:
        _engine = create_engine(
            f'sqlite:///{current_path}',
            connect_args={'check_same_thread': False},
        )
        _engine_path = current_path
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


@contextmanager
def session_scope():
    with Session(get_engine()) as session:
        yield session
