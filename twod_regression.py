import os
import re
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

# Escape form so this script stays safe under any console/file encoding.
MYANMAR_LABEL = ('မြန်မာစံတော်')

fails = []


def check(label, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + label + (('  -> ' + detail) if detail else ''))
    if not ok:
        fails.append(label)


User = get_user_model()
c = Client()
c.force_login(User.objects.get(username='solo'))

print('--- owner pages ---')
pages = ['/bet/?type=dealer', '/bet/?type=bettor', '/bet/', '/records/', '/ledger/', '/settings/', '/chat/', '/bet/settings/']
for url in pages:
    r = c.get(url)
    check(f'{url} renders', r.status_code == 200, f'status={r.status_code}')

print('--- brand rename ---')
for url in ['/bet/?type=dealer', '/bet/?type=bettor', '/bet/']:
    b = c.get(url).content.decode()
    check(f'{url} shows 2DAP-3SPRO', '2DAP-3SPRO' in b)
    check(f'{url} old name gone', '2D Formula Parser' not in b and 'Parser Engine' not in b)

print('--- nav logout + clock removals ---')
for url in ['/bet/?type=dealer', '/bet/?type=bettor']:
    b = c.get(url).content.decode()
    check(f'{url} no logout form', 'logout' not in b.lower())
for url in ['/records/', '/ledger/']:
    b = c.get(url).content.decode()
    check(f'{url} no logout', 'logout' not in b.lower())
    check(f'{url} no thailand clock', 'Digital Clock (Thailand)' not in b)
    check(f'{url} no myanmar clock block', 'Digital Clock (Myanmar)' not in b)

print('--- thai 2d live ticker consistency ---')
for url in ['/bet/?type=dealer', '/records/', '/ledger/']:
    b = c.get(url).content.decode()
    check(f'{url} has tickerTime', 'id="tickerTime"' in b)
    check(f'{url} has tickerNext', 'id="tickerNext"' in b)
    check(f'{url} has myanmar label', MYANMAR_LABEL in b)
    check(f'{url} has drawState()', 'function drawState' in b)
    check(f'{url} has buildSchedule()', 'function buildSchedule' in b)
    check(f'{url} schedules seeded', 'buildSchedule(null)' in b)
    bodies = b.split('setInterval(')[1:]
    one_second_bodies = [body[:600] for body in bodies if ', 1000)' in body[:600]]
    has_tick = any('updateTicker' in body for body in one_second_bodies)
    check(f'{url} ticks every second', has_tick, f'oneSecondIntervals={len(one_second_bodies)}')
    check(f'{url} uses myanmar offset', 'MYANMAR_OFFSET_SEC = 1800' in b)
    check(f'{url} labels 2DAP ticker', 'Thai 2D Live' in b)

print('--- player settings admin gating ---')
owner_settings = c.get('/settings/').content.decode()
check('owner settings shows Administration', 'Administration' in owner_settings)
check('owner settings links to admin console', '/app/admin/' in owner_settings)
check('owner settings shows Owner role badge', re.search(r'>\s*Owner\s*<', owner_settings) is not None)
owner_group_count = owner_settings.count('class="settings-group-title"')
check('owner settings shows all 5 groups', owner_group_count == 5, f'groups={owner_group_count}')

print('--- player role settings must not leak admin ---')
from twodapp.models import BettorAccount  # noqa: E402

USERNAME = 'qa_tmp_settings'
PASSWORD = 'qa-tmp-pass'
existing = BettorAccount.objects.filter(username=USERNAME).first()
created = existing is None
if created:
    acc = BettorAccount.objects.create(username=USERNAME, balance=0, is_active=True)
    acc.set_password(PASSWORD)
    acc.save()

try:
    import json as _json
    pc = Client()
    r = pc.post('/api/bettor_login', data=_json.dumps({'username': USERNAME, 'password': PASSWORD}),
                content_type='application/json')
    check('player login', r.status_code == 200 and r.json().get('ok') is True)
    b = pc.get('/bet/settings/').content.decode()
    check('player settings renders', len(b) > 0)
    check('player settings hides Administration', 'Administration' not in b)
    check('player settings hides admin console link', '/app/admin/' not in b)
    check('player settings hides delete owner buttons', 'delete_owner' not in b)
    check('player settings shows Player role badge', re.search(r'>\s*Player\s*<', b) is not None)
    player_group_count = b.count('class="settings-group-title"')
    check('player settings has 3 groups', player_group_count == 3, f'groups={player_group_count}')
    pb = pc.get('/bet/?type=bettor').content.decode()
    check('player home has no logout', 'logout' not in pb.lower())
    check('player home shows 2DAP-3SPRO', '2DAP-3SPRO' in pb)
    cb = pc.get('/bet/chat/').content.decode()
    check('player chat badge visible on mobile (no hidden sm:flex)', 'id="senderName"' in cb and 'sm:flex items-center gap-1 text-[10px] bg-white/20' not in cb)
    check('player chat has exactly one senderName', cb.count('id="senderName"') == 1)
    check('player chat navbar shows user-circle icon', 'fa-user-circle' in cb)
    r = pc.get('/api/bettor_profile')
    check('player profile API 200 JSON', r.status_code == 200 and '"ok":true' in r.content.decode().replace('"ok": true', '"ok":true'))
    check('player profile returns username', r.json().get('account', {}).get('username') == USERNAME)
    r2 = Client().get('/api/bettor_profile')
    check('anon profile API 403 not 302', r2.status_code == 403, f'status={r2.status_code}')
finally:
    if created:
        BettorAccount.objects.filter(username=USERNAME).delete()
        print('player fixture deleted')

print('--- multiplier field ---')
check('model default is 80', re.search(r'multiplier\s*=\s*models\.(IntegerField|PositiveIntegerField)\([^)]*default=80', open(os.path.join(os.path.dirname(__file__), 'twodapp', 'models.py'), encoding='utf-8').read(), re.S) is not None)
import twodapp.models as _m  # noqa: E402
field = _m.BettorAccount._meta.get_field('multiplier')
check('multiplier default 80', field.default == 80, f'default={field.default}')

print()
print('RESULT:', 'ALL CHECKS PASSED' if not fails else f'{len(fails)} FAILED -> {fails}')
sys.exit(0 if not fails else 1)
