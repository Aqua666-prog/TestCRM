import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.config import Settings
from app.main import create_app
from app.models import Lead, Tag


@pytest.fixture
def setup(tmp_path):
    settings = Settings(database_url='sqlite:///' + str(tmp_path / 'test.db'),
        crm_password='test-password', telegram_webhook_secret='test-webhook-secret')
    replies = []
    app = create_app(settings, sender=lambda chat, reply: replies.append((chat, reply)))
    with TestClient(app) as client:
        client.auth = ('admin', 'test-password')
        yield app, client, replies, settings


def csrf(client):
    return re.search(r'name="csrf" value="([^"]+)"', client.get('/').text).group(1)


def message(client, number, value=None, contact=None, secret='test-webhook-secret'):
    msg = {'chat': {'id': 12345, 'type': 'private'}}
    if value is not None:
        msg['text'] = value
    if contact:
        msg['contact'] = {'phone_number': contact}
    return client.post('/telegram/webhook', headers={'X-Telegram-Bot-Api-Secret-Token': secret},
                       json={'update_id': number, 'message': msg})


def add_tag(client, name):
    assert client.post('/tags', data={'name': name, 'csrf': csrf(client)}).status_code == 200


def test_full_telegram_to_crm_tag_filter_and_manual(setup):
    app, client, replies, _ = setup
    for number, value in enumerate(['/start', 'Сергей', '@sergey', 'Нужен сайт музея'], 1):
        assert message(client, number, value).status_code == 200
    assert ['Как вас зовут' in replies[0][1], 'Как с вами' in replies[1][1],
            'Опишите' in replies[2][1], 'Заявка №' in replies[3][1]] == [True] * 4
    html = client.get('/').text
    assert 'Сергей' in html and 'Нужен сайт музея' in html and 'Telegram' in html
    with app.state.sessions() as db:
        lead = db.scalar(select(Lead))
        assert lead.source == 'telegram_bot' and lead.telegram_chat_id == 12345
        lead_id = lead.id
    assert client.post('/leads', data={'csrf': csrf(client), 'name': 'Анна',
        'contact': 'anna@example.com', 'request_text': 'Логотип'}).status_code == 200
    add_tag(client, 'Дизайн')
    add_tag(client, 'Срочно')
    with app.state.sessions() as db:
        tags = db.scalars(select(Tag).order_by(Tag.id)).all()
        ids = [t.id for t in tags]
        manual = db.scalar(select(Lead).where(Lead.source == 'manual'))
        assert manual.name == 'Анна' and manual.telegram_chat_id is None
    assert client.post(f'/leads/{lead_id}/tags', data={'csrf': csrf(client), 'tag_ids': [str(x) for x in ids]}).status_code == 200
    filtered = client.get('/?tag_id=' + str(ids[0])).text
    assert 'Нужен сайт музея' in filtered and 'Логотип' not in filtered
    with app.state.sessions() as db:
        assert len(db.get(Lead, lead_id).tags) == 2
    assert 'Логотип' in client.get('/?tag_id=').text
    assert client.post(f'/leads/{lead_id}/tags', data={'csrf': csrf(client)}).status_code == 200
    assert 'Нужен сайт музея' not in client.get('/?tag_id=' + str(ids[0])).text


def test_duplicate_update_does_not_duplicate_lead_or_reply(setup):
    app, client, replies, _ = setup
    for n, value in enumerate(['/start', 'Имя', 'Контакт', 'Запрос'], 10):
        assert message(client, n, value).status_code == 200
    assert message(client, 13, 'Запрос').status_code == 200
    assert len(replies) == 4
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Lead)) == 1


def test_delivery_retry_commits_only_one_lead(setup):
    app, client, replies, _ = setup
    for n, value in enumerate(['/start', 'Имя', 'Контакт'], 20):
        message(client, n, value)
    def unavailable(chat, reply):
        raise RuntimeError('Network unavailable')
    app.state.sender = unavailable
    assert message(client, 23, 'Запрос').status_code == 503
    app.state.sender = lambda chat, reply: replies.append((chat, reply))
    assert message(client, 23, 'Запрос').status_code == 200
    assert len(replies) == 4
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Lead)) == 1


def test_conversation_survives_restart(setup):
    app, client, replies, settings = setup
    message(client, 30, '/start')
    message(client, 31, 'После перезапуска')
    second_app = create_app(settings, sender=lambda chat, reply: replies.append((chat, reply)))
    with TestClient(second_app) as second:
        assert message(second, 32, contact='+79991234567').status_code == 200
        assert message(second, 33, 'Запрос после перезапуска').status_code == 200
    with app.state.sessions() as db:
        lead = db.scalar(select(Lead))
        assert lead.name == 'После перезапуска' and lead.contact == '+79991234567'


def test_validation_and_cancel(setup):
    app, client, replies, _ = setup
    message(client, 40, '/start')
    message(client, 41, 'x' * 101)
    assert 'от 1 до 100' in replies[-1][1]
    message(client, 42, 'Имя')
    message(client, 43, ' ')
    assert 'от 1 до 200' in replies[-1][1]
    message(client, 44, 'Контакт')
    message(client, 45, 'x' * 4001)
    assert 'от 1 до 4000' in replies[-1][1]
    message(client, 46, '/cancel')
    assert client.post('/leads', data={'csrf': csrf(client), 'name': ' ', 'contact': 'c', 'request_text': 'r'}).status_code == 422
    assert client.post('/tags', data={'csrf': csrf(client), 'name': ' '}).status_code == 422
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Lead)) == 0


def test_security_and_escaping(setup):
    app, client, replies, _ = setup
    assert client.get('/', auth=('bad', 'bad')).status_code == 401
    assert client.post('/leads', data={'name': 'n', 'contact': 'c', 'request_text': 'r'}).status_code == 403
    assert message(client, 50, '/start', secret='wrong').status_code == 403
    assert client.post('/leads', data={'csrf': csrf(client), 'name': '<script>alert(1)</script>', 'contact': 'c', 'request_text': 'r'}).status_code == 200
    assert '<script>alert(1)</script>' not in client.get('/').text
    assert '&lt;script&gt;' in client.get('/').text
    assert client.get('/health', auth=('bad', 'bad')).json() == {'status': 'ok'}


def test_tags_deduplicate_and_reject_unknown(setup):
    app, client, replies, _ = setup
    add_tag(client, ' ДИЗАЙН ')
    add_tag(client, 'дизайн')
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Tag)) == 1
    assert client.post('/leads', data={'csrf': csrf(client), 'name': 'n', 'contact': 'c', 'request_text': 'r'}).status_code == 200
    assert client.post('/leads/1/tags', data={'csrf': csrf(client), 'tag_ids': '999'}).status_code == 422
    assert client.post('/leads/999/tags', data={'csrf': csrf(client)}).status_code == 404
    assert client.get('/?tag_id=wrong').status_code == 422


def test_unsupported_update_ignored(setup):
    _, client, replies, _ = setup
    assert client.post('/telegram/webhook', headers={'X-Telegram-Bot-Api-Secret-Token': 'test-webhook-secret'},
                       json={'update_id': 60, 'callback_query': {}}).status_code == 200
    assert not replies


def test_production_requires_secrets_and_postgres():
    with pytest.raises(ValueError):
        create_app(Settings(app_env='production'))
