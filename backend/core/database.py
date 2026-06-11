from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from core.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def _migrate_db() -> None:
    """Forward-compatible column additions for SQLite (no Alembic required)."""
    import sqlite3
    db_path = str(DATABASE_URL).replace("sqlite:///", "")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(generated_videos)")
        existing = {row[1] for row in cursor.fetchall()}
        additions = [
            ("queued_at", "DATETIME"),
            ("last_progress_at", "DATETIME"),
        ]
        for col, col_type in additions:
            if col not in existing:
                cursor.execute(
                    f"ALTER TABLE generated_videos ADD COLUMN {col} {col_type}"
                )
        conn.commit()
        conn.close()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"[DB Migration] Could not apply migrations: {exc}")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
