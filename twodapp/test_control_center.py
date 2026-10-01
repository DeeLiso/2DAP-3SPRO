"""Temporary verification harness for the Control Center hardening batches.

Run with:  python manage.py test twodapp.test_control_center
Delete after the run; kept out of the repo on purpose.
"""

import json

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import Client, TestCase

from twodapp.models import BettorAccount, ControlCenterAudit


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


class ControlCenterSecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', 'root@example.com', 'RootPass123!')
        self.client = Client()
        self.client.force_login(self.admin)

    def make_bettor(self, username='b1', password='BettorPass123!'):
        acc = BettorAccount(username=username)
        acc.set_password(password)
        acc.balance = 500
        acc.save()
        return acc

    def make_bettor_session(self, acc):
        store = SessionStore()
        store['bettor_account_id'] = acc.pk
        store.save()
        return store

    def make_user_session(self, user):
        store = SessionStore()
        store['_auth_user_id'] = str(user.pk)
        store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        store.save()
        return store

    def bettor_session_keys(self):
        out = set()
        decoder = SessionStore()
        for key, blob in Session.objects.values_list('session_key', 'session_data'):
            try:
                data = decoder.decode(blob)
            except Exception:
                continue
            if isinstance(data, dict) and 'bettor_account_id' in data:
                out.add(key)
        return out

    def user_session_keys(self):
        out = set()
        decoder = SessionStore()
        for key, blob in Session.objects.values_list('session_key', 'session_data'):
            try:
                data = decoder.decode(blob)
            except Exception:
                continue
            if isinstance(data, dict) and '_auth_user_id' in data:
                out.add(key)
        return out

    # --- bettor lifecycle -------------------------------------------------

    def test_suspend_revokes_bettor_sessions(self):
        acc = self.make_bettor()
        self.make_bettor_session(acc)
        self.make_bettor_session(acc)
        self.assertEqual(len(self.bettor_session_keys()), 2)

        res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'is_active': False})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['sessions_revoked'], 2)
        self.assertEqual(self.bettor_session_keys(), set())

    def test_activate_also_revokes(self):
        acc = self.make_bettor()
        BettorAccount.objects.filter(pk=acc.pk).update(is_active=False)
        self.make_bettor_session(acc)
        res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'is_active': True})
        self.assertEqual(res.json()['sessions_revoked'], 1)
        self.assertEqual(self.bettor_session_keys(), set())

    def test_bettor_password_change_revokes(self):
        acc = self.make_bettor()
        self.make_bettor_session(acc)
        res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'password': 'Rotated123!'})
        self.assertEqual(res.json()['sessions_revoked'], 1)
        acc.refresh_from_db()
        self.assertTrue(acc.check_password('Rotated123!'))

    def test_delete_bettor_revokes_and_removes(self):
        acc = self.make_bettor()
        self.make_bettor_session(acc)
        pk = acc.pk
        res = post_json(self.client, '/api/delete_bettor', {'id': pk})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['sessions_revoked'], 1)
        self.assertFalse(BettorAccount.objects.filter(pk=pk).exists())
        self.assertEqual(self.bettor_session_keys(), set())

    def test_suspended_bettor_session_is_terminated(self):
        # /api/parse is guarded by api_login_required, which answers 403 for an
        # unauthenticated caller, so the assertion is unambiguous.
        acc = self.make_bettor()
        session = self.make_bettor_session(acc)
        player = Client()
        player.cookies[settings_session_cookie()] = session.session_key
        self.assertEqual(player.post('/api/parse', data=json.dumps({'numbers': [1, 2]}),
                                     content_type='application/json').status_code, 200,
                         msg='bettor session should work before suspension')

        post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'is_active': False})
        # The session row was deleted, so the old cookie no longer authenticates.
        self.assertEqual(player.post('/api/parse', data=json.dumps({'numbers': [1, 2]}),
                                     content_type='application/json').status_code, 403)

    def test_superuser_cannot_demote_themselves(self):
        res = post_json(self.client, '/api/edit_operator', {'id': self.admin.pk, 'is_superuser': False})
        self.assertFalse(res.json()['ok'])
        self.assertIn('your own', res.json()['error'])
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    def test_superuser_profile_edit_still_works(self):
        res = post_json(self.client, '/api/edit_operator', {'id': self.admin.pk, 'first_name': 'Root', 'last_name': 'Admin'})
        self.assertTrue(res.json()['ok'])
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.first_name, 'Root')

    # --- owner lifecycle --------------------------------------------------

    def test_owner_password_reset_revokes_sessions(self):
        owner = User.objects.create_user('own1', password='OwnerPass123!')
        self.make_user_session(owner)
        res = post_json(self.client, '/api/reset_operator_password', {'id': owner.pk, 'password': 'FreshPass123!'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['sessions_revoked'], 1)
        self.assertEqual(self.user_session_keys(), {self.client.session.session_key})

    def test_owner_suspend_revokes_sessions(self):
        owner = User.objects.create_user('own2', password='OwnerPass123!')
        self.make_user_session(owner)
        res = post_json(self.client, '/api/edit_operator', {'id': owner.pk, 'is_active': False})
        self.assertEqual(res.json()['sessions_revoked'], 1)
        owner.refresh_from_db()
        self.assertFalse(owner.is_active)

    def test_last_active_superuser_is_protected(self):
        # You cannot lock yourself out.
        res = post_json(self.client, '/api/edit_operator', {'id': self.admin.pk, 'is_superuser': False})
        self.assertFalse(res.json()['ok'])
        res = post_json(self.client, '/api/edit_operator', {'id': self.admin.pk, 'is_active': False})
        self.assertFalse(res.json()['ok'])
        res = post_json(self.client, '/api/delete_operator', {'id': self.admin.pk})
        self.assertFalse(res.json()['ok'])
        self.assertTrue(User.objects.filter(pk=self.admin.pk, is_superuser=True, is_active=True).exists())

    def test_demoting_another_superuser_is_allowed_when_one_remains(self):
        # The actor is an active superuser, so demoting a peer always leaves at
        # least the actor behind. That is the intended behaviour.
        second = User.objects.create_superuser('root2', 'r2@example.com', 'Root2Pass123!')
        client = Client()
        client.force_login(second)
        res = post_json(client, '/api/edit_operator', {'id': self.admin.pk, 'is_superuser': False})
        self.assertTrue(res.json()['ok'])
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)
        self.assertEqual(User.objects.filter(is_superuser=True, is_active=True).count(), 1)

    def test_last_superuser_guard_blocks_when_none_would_remain(self):
        from twodapp.views import _last_superuser_guard

        self.assertEqual(_last_superuser_guard(self.admin, False, True),
                         'At least one active superuser must remain.')
        self.assertEqual(_last_superuser_guard(self.admin, True, False),
                         'At least one active superuser must remain.')
        self.assertEqual(_last_superuser_guard(self.admin, True, True), '')

        # A peer superuser exists, so the change is safe.
        User.objects.create_superuser('root2', 'r2@example.com', 'Root2Pass123!')
        self.assertEqual(_last_superuser_guard(self.admin, False, True), '')

        # Non-superusers are never guarded.
        plain = User.objects.create_user('plain', password='PlainPass123!')
        self.assertEqual(_last_superuser_guard(plain, False, False), '')

    def test_suspending_the_only_other_superuser_is_blocked(self):
        # actor = self.admin, target = root2, and the actor is the one asking, so
        # root2 is the only superuser that could be lost from the target side.
        second = User.objects.create_superuser('root2', 'r2@example.com', 'Root2Pass123!')
        second_client = Client()
        second_client.force_login(second)
        res = post_json(self.client, '/api/edit_operator', {'id': second.pk, 'is_superuser': False})
        self.assertTrue(res.json()['ok'])
        second.refresh_from_db()
        self.assertFalse(second.is_superuser)

    def test_non_superuser_cannot_reach_admin_api(self):
        staff = User.objects.create_user('clerk', password='ClerkPass123!')
        other = Client()
        other.force_login(staff)
        res = post_json(other, '/api/create_bettor', {'username': 'x', 'password': 'Abcd1234!', 'balance': 0})
        self.assertEqual(res.status_code, 403)

    # --- validation -------------------------------------------------------

    def test_bettor_create_enforces_password_policy(self):
        res = post_json(self.client, '/api/create_bettor', {'username': 'shorty', 'password': 'abc', 'balance': 0})
        self.assertFalse(res.json()['ok'])
        self.assertIn('8', res.json()['error'])
        self.assertFalse(BettorAccount.objects.filter(username='shorty').exists())

    def test_bettor_edit_enforces_password_policy(self):
        acc = self.make_bettor()
        res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'password': '12345678'})
        self.assertFalse(res.json()['ok'])
        acc.refresh_from_db()
        self.assertTrue(acc.check_password('BettorPass123!'))

    def test_bettor_create_rejects_bad_balance(self):
        for bad in [-1, 'abc', 1.5, 2147483648, True, None]:
            res = post_json(self.client, '/api/create_bettor', {'username': f'bad{bad}', 'password': 'Abcd1234!', 'balance': bad})
            self.assertFalse(res.json()['ok'], msg=f'balance={bad!r} was accepted')

    def test_bettor_edit_rejects_bad_balance(self):
        acc = self.make_bettor()
        res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'balance': '1.5'})
        self.assertFalse(res.json()['ok'])
        acc.refresh_from_db()
        self.assertEqual(acc.balance, 500)

    def test_bettor_edit_blank_balance_keeps_current(self):
        acc = self.make_bettor()
        res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'balance': ''})
        self.assertTrue(res.json()['ok'])
        acc.refresh_from_db()
        self.assertEqual(acc.balance, 500)

    def test_hot_limits_normalisation_and_rejection(self):
        acc = self.make_bettor()
        res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'hot_limits': {'5': 100, '44': 3000}})
        self.assertTrue(res.json()['ok'])
        acc.refresh_from_db()
        self.assertEqual(acc.hot_limits, {'05': 100, '44': 3000})

        for bad in [{'100': 1}, {'5': -1}, {'5': 1.5}, {'5': 'x'}, {'05': 1, '5': 2}]:
            res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'hot_limits': bad})
            self.assertFalse(res.json()['ok'], msg=f'hot_limits={bad!r} was accepted')
        acc.refresh_from_db()
        self.assertEqual(acc.hot_limits, {'05': 100, '44': 3000})

    def test_is_active_is_strict_boolean(self):
        res = post_json(self.client, '/api/create_bettor', {'username': 'flagged', 'password': 'Abcd1234!', 'is_active': 'yes-please'})
        self.assertFalse(res.json()['ok'])
        res = post_json(self.client, '/api/create_operator', {'username': 'flagop', 'password': 'Abcd1234!', 'is_active': 'nope'})
        self.assertFalse(res.json()['ok'])
        self.assertFalse(User.objects.filter(username='flagop').exists())

    def test_create_operator_persists_is_active(self):
        res = post_json(self.client, '/api/create_operator', {'username': 'newop', 'password': 'Abcd1234!', 'is_active': False})
        self.assertTrue(res.json()['ok'])
        self.assertFalse(User.objects.get(username='newop').is_active)

    # --- audit trail ------------------------------------------------------

    def test_audit_rows_are_written(self):
        acc = self.make_bettor()
        post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'balance': 1234})
        post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'is_active': False})
        post_json(self.client, '/api/delete_bettor', {'id': acc.pk})

        actions = list(
            ControlCenterAudit.objects
            .filter(actor_id=self.admin.pk, target_type='player')
            .values_list('action', flat=True)
        )
        self.assertIn('update', actions)
        self.assertIn('suspend', actions)
        self.assertIn('delete', actions)

    def test_audit_never_breaks_the_request(self):
        acc = self.make_bettor()
        original = ControlCenterAudit.objects.create
        ControlCenterAudit.objects.create = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('audit down'))
        try:
            res = post_json(self.client, '/api/edit_bettor', {'id': acc.pk, 'balance': 77})
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()['ok'])
        finally:
            ControlCenterAudit.objects.create = original


def settings_session_cookie():
    from django.conf import settings
    return settings.SESSION_COOKIE_NAME


class BettorSettingsLimitAlarmTests(TestCase):
    """The player settings page surfaces the owner-set hot limits, read-only."""

    def setUp(self):
        self.admin = User.objects.create_superuser('root', 'root@example.com', 'RootPass123!')
        self.client = Client()
        self.client.force_login(self.admin)
        self.acc = BettorAccount(username='alarmplayer')
        self.acc.set_password('AlarmPass123!')
        self.acc.save()

    def player_client(self):
        acc_id = self.acc.pk
        store = SessionStore()
        store['bettor_account_id'] = acc_id
        store['bettor_username'] = self.acc.username
        store.save()
        c = Client()
        c.cookies[settings_session_cookie()] = store.session_key
        return c

    def set_limits(self, limits):
        res = post_json(self.client, '/api/edit_bettor', {'id': self.acc.pk, 'hot_limits': limits})
        self.assertTrue(res.json()['ok'], msg=res.content)

    def test_alarm_card_hidden_when_no_limits(self):
        body = self.player_client().get('/bet/settings/').content.decode()
        self.assertNotIn('Limit Alarm', body)
        self.assertEqual(self.player_client().get('/bet/settings/').status_code, 200)

    def test_alarm_card_lists_owner_limits(self):
        self.set_limits({'44': 3000, '5': 5000, '23': 15000})
        body = self.player_client().get('/bet/settings/').content.decode()
        self.assertIn('Limit Alarm', body)
        self.assertIn('fa-bell', body)
        for num, amount in (('05', '5,000'), ('23', '15,000'), ('44', '3,000')):
            self.assertIn(f'ဂဏန်း {num}', body, msg=f'number {num} missing')
            self.assertIn(f'{amount} Ks', body, msg=f'amount {amount} missing')
        # Sorted numerically: 05, then 23, then 44.
        self.assertLess(body.index('ဂဏန်း 05'), body.index('ဂဏန်း 23'))
        self.assertLess(body.index('ဂဏန်း 23'), body.index('ဂဏန်း 44'))

    def test_alarm_card_has_no_edit_controls(self):
        self.set_limits({'23': 5000})
        body = self.player_client().get('/bet/settings/').content.decode()
        # Read-only: no input/button that could post a limit change.
        self.assertNotIn('id="bettorHotLimits"', body)
        self.assertNotIn('saveHotLimits', body)
        self.assertIn('မရှိပါ', body)

    def test_alarm_card_hidden_from_owner_page(self):
        self.set_limits({'23': 5000})
        owner = User.objects.create_superuser('boss', 'b@e.com', 'BossPass123!')
        oc = Client()
        oc.force_login(owner)
        body = oc.get('/settings/').content.decode()
        self.assertNotIn('Limit Alarm', body)

    def test_sort_is_numeric_not_lexicographic(self):
        # Lexicographic would give 05, 23, 9; numeric must give 05, 09, 23.
        self.set_limits({'9': 100, '23': 200, '5': 300})
        body = self.player_client().get('/bet/settings/').content.decode()
        self.assertLess(body.index('ဂဏန်း 05'), body.index('ဂဏန်း 09'))
        self.assertLess(body.index('ဂဏန်း 09'), body.index('ဂဏန်း 23'))
