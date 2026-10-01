"""Real HTTP smoke test. Creates TWO test leads and TWO tags; does not call Telegram.
Run against a local development server. Never use a real webhook secret here.
"""
import os
import re
import secrets
import time
import httpx


def main():
    base = os.getenv('SMOKE_BASE_URL', 'http://127.0.0.1:8000')
    if not base.startswith(('http://127.0.0.1:', 'http://localhost:')):
        raise SystemExit('Synthetic webhook smoke is limited to localhost. Use a real bot in production.')
    suffix = secrets.token_hex(4)
    with httpx.Client(base_url=base, auth=(os.getenv('CRM_USERNAME', 'admin'),
                      os.getenv('CRM_PASSWORD', 'change-me-local')), follow_redirects=True, trust_env=False) as client:
        def token():
            return re.search(r'name="csrf" value="([^"]+)"', client.get('/').text).group(1)
        assert client.get('/health').json() == {'status': 'ok'}
        headers = {'X-Telegram-Bot-Api-Secret-Token': os.environ['TELEGRAM_WEBHOOK_SECRET']}
        update_id = int(time.time() * 1000)
        # A running DEVELOPMENT server with an injected test sender is required.
        for offset, value in enumerate(['/start', 'Smoke Telegram ' + suffix, '@smoke', 'Request ' + suffix]):
            response = client.post('/telegram/webhook', headers=headers, json={
                'update_id': update_id + offset,
                'message': {'chat': {'id': update_id, 'type': 'private'}, 'text': value}})
            response.raise_for_status()
        response = client.post('/leads', data={'csrf': token(), 'name': 'Smoke Manual ' + suffix,
            'contact': 'manual@example.org', 'request_text': 'Manual ' + suffix})
        response.raise_for_status()
        html = client.get('/').text
        assert 'Smoke Telegram ' + suffix in html and 'Smoke Manual ' + suffix in html
        lead_id = re.search(r'id="lead-(\d+)"[^>]*>\s*<div class="lead-top"><h3>Smoke Telegram ' + suffix, html).group(1)
        for name in ['smoke-' + suffix, 'second-' + suffix]:
            client.post('/tags', data={'csrf': token(), 'name': name}).raise_for_status()
        html = client.get('/').text
        tags = [re.search(r'<option value="(\d+)"[^>]*>' + name + '</option>', html).group(1)
                for name in ['smoke-' + suffix, 'second-' + suffix]]
        client.post('/leads/' + lead_id + '/tags', data={'csrf': token(), 'tag_ids': tags}).raise_for_status()
        html = client.get('/?tag_id=' + tags[0]).text
        assert 'Smoke Telegram ' + suffix in html and 'Smoke Manual ' + suffix not in html
    print('PASS: running HTTP server → Telegram intake → CRM → two tags → filter; manual creation.')


if __name__ == '__main__':
    main()
