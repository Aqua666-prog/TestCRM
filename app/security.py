import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException


def csrf_token(secret):
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    return timestamp + '.' + signature


def check_csrf(secret, token):
    try:
        timestamp, signature = token.split('.')
        age = int(time.time()) - int(timestamp)
        expected = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
        valid = 0 <= age <= 7200 and secrets.compare_digest(signature, expected)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise HTTPException(403, 'Форма устарела. Обновите страницу и повторите действие.')
