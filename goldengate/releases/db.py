"""SQLite persistence (SQLAlchemy 2.x): releases, runs, metrics, settings and judge cache."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from goldengate import paths
from goldengate.core.models import utcnow


class Base(DeclarativeBase):
    pass


class ReleaseRow(Base):
    __tablename__ = "releases"

    release_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, default="")
    system: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(200))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    retriever_config: Mapped[dict] = mapped_column(JSON, default=dict)
    released_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    runs: Mapped[list[RunRow]] = relationship(back_populates="release", cascade="all, delete-orphan")


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.release_id"))
    golden_version: Mapped[str] = mapped_column(String(20))
    golden_hash: Mapped[str] = mapped_column(String(64))
    git_commit: Mapped[str] = mapped_column(String(64))
    judge_mode: Mapped[str] = mapped_column(String(40))
    judges_used: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    n_items: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result_path: Mapped[str] = mapped_column(Text)
    release: Mapped[ReleaseRow] = relationship(back_populates="runs")
    metrics: Mapped[list[MetricRow]] = relationship(back_populates="run", cascade="all, delete-orphan")


class MetricRow(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    n: Mapped[int] = mapped_column(Integer, default=0)
    run: Mapped[RunRow] = relationship(back_populates="metrics")


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class JudgeCacheRow(Base):
    __tablename__ = "judge_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    rubric_version: Mapped[str] = mapped_column(String(40))
    item_id: Mapped[str] = mapped_column(String(120))
    answer_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_ENGINES: dict[str, Engine] = {}


def engine(db_file: Path | None = None) -> Engine:
    """Engine for the workspace database (created with tables on first use)."""
    path = str(db_file or paths.db_path())
    if path not in _ENGINES:
        eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(eng)
        _ENGINES[path] = eng
    return _ENGINES[path]


def session(db_file: Path | None = None) -> Session:
    return Session(engine(db_file), expire_on_commit=False)


def dispose_engines() -> None:
    """Close pooled connections (needed before deleting the database file on Windows)."""
    for eng in _ENGINES.values():
        eng.dispose()
    _ENGINES.clear()


class SqlJudgeCache:
    """Judge cache stored in the ``judge_cache`` table."""

    def __init__(self, db_file: Path | None = None) -> None:
        self.db_file = db_file

    def get(self, key: str) -> str | None:
        with session(self.db_file) as s:
            row = s.get(JudgeCacheRow, key)
            return row.payload if row else None

    def put(self, key: str, rubric_version: str, item_id: str, answer_hash: str, payload: str) -> None:
        with session(self.db_file) as s:
            s.merge(JudgeCacheRow(key=key, rubric_version=rubric_version, item_id=item_id,
                                  answer_hash=answer_hash, payload=payload))
            s.commit()

    def count(self) -> int:
        with session(self.db_file) as s:
            return len(s.scalars(select(JudgeCacheRow.key)).all())
