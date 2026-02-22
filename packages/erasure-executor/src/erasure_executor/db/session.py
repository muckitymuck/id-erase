from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_session_factory(database_url: str):
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory, engine
