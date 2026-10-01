import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from .config import Settings
from .db import Base, database
from .leads import LeadInput, create_lead, list_leads
from .models import Lead, Tag
from .security import csrf_token, check_csrf
from .telegram import router as telegram_router

ROOT = Path(__file__).parent


def create_app(settings=None, sender=None):
    settings = settings or Settings()
    settings.validate_production()
    engine, sessions = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title='Agency CRM', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(telegram_router)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.engine = engine
    app.state.sender = sender
    templates = Jinja2Templates(directory=ROOT / 'templates')
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
    basic = HTTPBasic()

    def authenticate(credentials: HTTPBasicCredentials = Depends(basic)):
        valid_user = secrets.compare_digest(credentials.username.encode(), settings.crm_username.encode())
        valid_password = secrets.compare_digest(credentials.password.encode(), settings.crm_password.encode())
        if not (valid_user and valid_password):
            raise HTTPException(401, 'Требуется вход', headers={'WWW-Authenticate': 'Basic realm="Agency CRM", charset="UTF-8"'})

    def get_db():
        with sessions() as db:
            yield db

    def page(request, db, error=None, values=None, status=200, tag_id=None):
        return templates.TemplateResponse(request=request, name='index.html', status_code=status,
            context={'leads': list_leads(db, tag_id), 'tags': db.scalars(select(Tag).order_by(Tag.name)).all(),
                     'active_tag': tag_id, 'csrf': csrf_token(settings.app_secret), 'error': error,
                     'values': values or {}, 'notice': request.query_params.get('notice', '')})

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse({'detail': 'Хранилище временно недоступно. Повторите позже.'}, status_code=503)

    @app.get('/health')
    def health(db=Depends(get_db)):
        db.execute(text('SELECT 1'))
        return {'status': 'ok'}

    @app.get('/', response_class=HTMLResponse, dependencies=[Depends(authenticate)])
    def index(request: Request, tag_id: int | None = None, db=Depends(get_db)):
        return page(request, db, tag_id=tag_id)

    @app.post('/leads', dependencies=[Depends(authenticate)])
    def manual(request: Request, name: str = Form(''), contact: str = Form(''),
               request_text: str = Form(''), csrf: str = Form(''), db=Depends(get_db)):
        check_csrf(settings.app_secret, csrf)
        values = {'name': name, 'contact': contact, 'request': request_text}
        try:
            data = LeadInput(**values, source='manual')
        except ValidationError:
            return page(request, db, error='Заполните все поля. Максимум: имя 100, контакт 200, запрос 4000 символов.', values=values, status=422)
        create_lead(db, data)
        db.commit()
        return RedirectResponse('/?notice=created', status_code=303)

    return app


app = create_app()
