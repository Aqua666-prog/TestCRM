from datetime import datetime, timezone
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Table, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

lead_tags = Table('lead_tags', Base.metadata,
    Column('lead_id', ForeignKey('leads.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True))


class Lead(Base):
    __tablename__ = 'leads'
    __table_args__ = (CheckConstraint("source IN ('manual', 'telegram_bot', 'telegram_account')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    contact: Mapped[str] = mapped_column(String(200))
    request: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tags: Mapped[list['Tag']] = relationship(secondary=lead_tags, lazy='selectin')


class Tag(Base):
    __tablename__ = 'tags'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)


class Conversation(Base):
    __tablename__ = 'conversations'
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    step: Mapped[str] = mapped_column(String(20), default='name')
    name: Mapped[str | None] = mapped_column(String(100))
    contact: Mapped[str | None] = mapped_column(String(200))


class TelegramUpdate(Base):
    __tablename__ = 'telegram_updates'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    reply: Mapped[str | None] = mapped_column(Text)
    delivered: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
