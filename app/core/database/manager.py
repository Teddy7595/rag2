from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database.base import DatabaseBase
from app.core.database.config import DatabaseSettings, load_database_settings
from app.core.settings import AppSettings


@dataclass(frozen=True)
class DatabaseManager:
    settings: DatabaseSettings
    engine: Engine
    session_factory: sessionmaker[Session]

    def create_schema(self) -> None:
        DatabaseBase.metadata.create_all(bind=self.engine)

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def build_database_manager(app_settings: AppSettings) -> DatabaseManager:
    database_settings = load_database_settings(app_settings)
    engine_options: dict[str, object] = {"echo": database_settings.echo}

    if database_settings.is_sqlite:
        engine_options["connect_args"] = {"check_same_thread": False}
    else:
        engine_options["pool_size"] = database_settings.pool_size
        engine_options["max_overflow"] = database_settings.max_overflow
        engine_options["pool_timeout"] = database_settings.pool_timeout
        engine_options["pool_pre_ping"] = True

    engine = create_engine(database_settings.url, **engine_options)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return DatabaseManager(
        settings=database_settings,
        engine=engine,
        session_factory=session_factory,
    )