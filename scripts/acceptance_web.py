"""Verify real production HTML forms. Creates clearly labelled acceptance data.

Run with production environment variables, never put credentials in arguments.
No synthetic Telegram updates are submitted: --telegram-name checks a real lead.
"""
import argparse
import os
import re
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--create-manual', action='store_true')
    parser.add_argument('--telegram-name')
    args = parser.parse_args()
    base = os.environ['PUBLIC_BASE_URL']
    if not base.startswith('https://'):
        raise SystemExit('Production acceptance requires HTTPS')
    with httpx.Client(base_url=base, timeout=30, follow_redirects=True,
                      auth=(os.environ['CRM_USERNAME'], os.environ['CRM_PASSWORD'])) as client:
        assert client.get('/health').json() == {'status': 'ok'}
        assert httpx.get(base, timeout=30).status_code == 401

        def page():
            response = client.get('/')
            response.raise_for_status()
            return response.text

        def csrf():
            return re.search(r'name="csrf" value="([^"]+)"', page()).group(1)

        def lead_id(name):
            match = re.search(r'id="lead-(\d+)"[^>]*>\s*<div class="lead-top"><h3>'
                              + re.escape(name) + r'</h3>', page())
            return match.group(1) if match else None

        manual_name = 'Приёмка MVP — вручную'
        if args.create_manual and not lead_id(manual_name):
            client.post('/leads', data={'csrf': csrf(), 'name': manual_name,
                'contact': 'manual-test@example.com', 'request_text': 'Проверка production HTML-формы'}).raise_for_status()
        if args.create_manual:
            assert lead_id(manual_name), 'Manual lead missing'
            print('PASS: HTTPS, database health, authentication, manual HTML form → CRM')

        target = args.telegram_name or manual_name
        target_id = lead_id(target)
        if target_id is None:
            print('WAITING: real Telegram lead is not yet visible in CRM')
            return
        if args.telegram_name:
            article = re.search(r'<article[^>]*id="lead-' + target_id + r'".*?</article>', page(), re.S).group(0)
            assert '<span class="source">Telegram</span>' in article
            assert 'test@example.com' in article and 'Нужен сайт для агентства' in article
        tag_names = ['приёмка mvp', 'тестирование']
        for name in tag_names:
            if not re.search(r'<option value="\d+"[^>]*>' + re.escape(name) + '</option>', page()):
                client.post('/tags', data={'csrf': csrf(), 'name': name}).raise_for_status()
        tags = [re.search(r'<option value="(\d+)"[^>]*>' + re.escape(name) + '</option>', page()).group(1)
                for name in tag_names]
        client.post('/leads/' + target_id + '/tags', data={'csrf': csrf(), 'tag_ids': tags}).raise_for_status()
        for tag_id in tags:
            filtered = client.get('/', params={'tag_id': tag_id})
            filtered.raise_for_status()
            assert 'id="lead-' + target_id + '"' in filtered.text
            if args.telegram_name:
                assert manual_name not in filtered.text
        unfiltered = page()
        assert target in unfiltered
        print('PASS: lead #' + target_id + ' → two tags → both filters → CRM')
        if not args.telegram_name:
            client.post('/leads/' + target_id + '/tags', data={'csrf': csrf()}).raise_for_status()
            print('PASS: remove tags from manual acceptance lead')


if __name__ == '__main__':
    try:
        main()
    except httpx.HTTPError:
        raise SystemExit('Acceptance HTTP request failed; credentials and token are not logged.') from None
