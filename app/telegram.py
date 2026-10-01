import secrets
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from .leads import LeadInput, create_lead
from .models import Conversation, TelegramUpdate

router = APIRouter()


class Chat(BaseModel):
    id: int = Field(ge=-(2**63), le=2**63-1)
    type: str


class Contact(BaseModel):
    phone_number: str


class Message(BaseModel):
    chat: Chat
    text: str | None = Field(default=None, max_length=8192)
    contact: Contact | None = None


class Update(BaseModel):
    model_config = ConfigDict(extra='ignore')
    update_id: int = Field(ge=0, le=2**63-1)
    message: Message | None = None


def lock_intake(db):
    # Short, serialized transactions are sufficient for this small MVP.
    # Lock also protects first-message creation and update deduplication.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(741239)'))
    else:
        db.execute(text('BEGIN IMMEDIATE'))


def intake(db, update):
    lock_intake(db)
    existing = db.get(TelegramUpdate, update.update_id)
    if existing:
        return existing
    record = TelegramUpdate(id=update.update_id)
    db.add(record)
    message = update.message
    if not message or message.chat.type != 'private':
        record.delivered = True
        return record
    chat_id = message.chat.id
    record.chat_id = chat_id
    conversation = db.get(Conversation, chat_id)
    value = (message.text or '').strip()
    if value in ('/start', '/new'):
        if conversation is None:
            conversation = Conversation(chat_id=chat_id)
            db.add(conversation)
        conversation.step, conversation.name, conversation.contact = 'name', None, None
        record.reply = 'Здравствуйте! Оставим заявку для агентства. Как вас зовут? Для отмены — /cancel.'
    elif value == '/cancel':
        if conversation:
            db.delete(conversation)
        record.reply = 'Заявка отменена. Для новой заявки отправьте /start.'
    elif value.startswith('/'):
        record.reply = 'Для новой заявки — /start. Для отмены — /cancel.'
    elif conversation is None:
        db.add(Conversation(chat_id=chat_id))
        record.reply = 'Здравствуйте! Как вас зовут? Для отмены — /cancel.'
    elif conversation.step == 'name':
        if not value or len(value) > 100:
            record.reply = 'Введите имя текстом: от 1 до 100 символов.'
        else:
            conversation.name, conversation.step = value, 'contact'
            record.reply = 'Как с вами связаться? Отправьте телефон, email или @username. Можно поделиться контактом.'
    elif conversation.step == 'contact':
        if message.contact:
            value = message.contact.phone_number.strip()
        if not value or len(value) > 200:
            record.reply = 'Отправьте контакт: от 1 до 200 символов.'
        else:
            conversation.contact, conversation.step = value, 'request'
            record.reply = 'Опишите, что нужно сделать: до 4000 символов.'
    else:
        if not value or len(value) > 4000:
            record.reply = 'Опишите запрос текстом: от 1 до 4000 символов.'
        else:
            lead = create_lead(db, LeadInput(name=conversation.name, contact=conversation.contact,
                                request=value, source='telegram_bot', telegram_chat_id=chat_id))
            db.delete(conversation)
            record.reply = f'Спасибо! Заявка №{lead.id} передана агентству. Для новой заявки — /start.'
    return record


def send_message(settings, chat_id, reply):
    if not settings.telegram_bot_token:
        raise RuntimeError('Telegram is not configured')
    # Never log URLs: Bot API puts the credential in the path.
    try:
        with httpx.Client(timeout=12) as client:
            response = client.post(f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage',
                                   json={'chat_id': chat_id, 'text': reply})
            if response.status_code != 200 or not response.json().get('ok'):
                raise RuntimeError('Telegram delivery failed')
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError('Telegram delivery failed') from None


@router.post('/telegram/webhook')
def webhook(request: Request, update: Update):
    settings = request.app.state.settings
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not settings.telegram_webhook_secret or not secrets.compare_digest(supplied, settings.telegram_webhook_secret):
        raise HTTPException(403, 'Invalid webhook secret')
    sessions = request.app.state.sessions
    with sessions() as db:
        record = intake(db, update)
        db.commit()  # State, lead and pending reply commit together before network I/O.
        if record.delivered or record.reply is None:
            return {'ok': True}
        sender = request.app.state.sender or (lambda chat, reply: send_message(settings, chat, reply))
        try:
            sender(record.chat_id, record.reply)
        except Exception:
            # Telegram retries the same update; intake returns its saved pending reply.
            raise HTTPException(503, 'Telegram delivery temporarily unavailable') from None
        record.delivered = True
        db.commit()
    return {'ok': True}
