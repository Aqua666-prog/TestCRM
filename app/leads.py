from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .models import Lead, Tag


class LeadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    contact: str = Field(min_length=1, max_length=200)
    request: str = Field(min_length=1, max_length=4000)
    source: Literal['manual', 'telegram_bot', 'telegram_account']
    telegram_chat_id: int | None = None


def create_lead(db, data: LeadInput):
    lead = Lead(**data.model_dump())
    db.add(lead)
    db.flush()
    return lead


def list_leads(db, tag_id=None):
    query = select(Lead).order_by(Lead.created_at.desc(), Lead.id.desc())
    if tag_id is not None:
        query = query.where(Lead.tags.any(Tag.id == tag_id))
    return db.scalars(query).all()
