"""Verification for player groups: owner scoping, the 10-player cap, dual role."""

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase

from twodapp.models import MAX_GROUP_PLAYERS, BettorAccount, PlayerGroup


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def create_group(admin_client, name, owner_id):
    return post_json(admin_client, '/api/create_group', {'name': name, 'owner_id': owner_id})


class PlayerGroupTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', 'root@example.com', 'RootPass123!')
        self.owner = User.objects.create_user('shopowner', 'o@example.com', 'OwnerPass123!', is_staff=True)
        self.rival = User.objects.create_user('rivalowner', 'r@example.com', 'RivalPass123!', is_staff=True)
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)
        self.owner_client = Client()
        self.owner_client.force_login(self.owner)

    def make_group(self, name='Shop A', owner=None):
        response = create_group(self.admin_client, name, (owner or self.owner).pk)
        self.assertEqual(response.status_code, 200, response.content)
        return PlayerGroup.objects.get(name=name)

    # --- group creation -------------------------------------------------
    def test_create_group_gives_owner_their_own_player_login(self):
        group = self.make_group()
        self.assertIsNotNone(group.owner_player)
        self.assertEqual(group.owner, self.owner)
        self.assertEqual(group.owner_player.group, group)
        self.assertTrue(group.owner_player.is_group_owner_player)
        self.assertEqual(group.player_count, 1)

    def test_owner_player_name_avoids_existing_player_name(self):
        BettorAccount.objects.create(username='shopowner', password_hash='x')
        group = self.make_group()
        self.assertNotEqual(group.owner_player.username, 'shopowner')
        self.assertTrue(group.owner_player.username.startswith('shopowner-'))

    def test_duplicate_group_name_rejected(self):
        self.make_group('Shop A')
        response = create_group(self.admin_client, 'Shop A', self.rival.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['ok'])

    def test_one_group_per_owner(self):
        self.make_group('Shop A')
        response = create_group(self.admin_client, 'Shop B', self.owner.pk)
        self.assertFalse(response.json()['ok'])
        self.assertEqual(PlayerGroup.objects.count(), 1)

    def test_group_needs_an_active_owner(self):
        self.owner.is_active = False
        self.owner.save()
        response = create_group(self.admin_client, 'Shop A', self.owner.pk)
        self.assertFalse(response.json()['ok'])

    def test_group_creation_is_superuser_only(self):
        response = create_group(self.owner_client, 'Mine', self.owner.pk)
        self.assertEqual(response.status_code, 403)

    # --- the 10-player cap ----------------------------------------------
    def test_cap_is_ten_including_the_owner_row(self):
        group = self.make_group()
        # owner row already occupies one slot
        for index in range(MAX_GROUP_PLAYERS - 1):
            response = post_json(self.owner_client, '/api/create_bettor', {
                'username': f'p{index}', 'password': 'PlayerPass123!', 'balance': 100,
            })
            self.assertTrue(response.json()['ok'], response.content)
        self.assertEqual(group.player_count, MAX_GROUP_PLAYERS)
        self.assertTrue(group.is_full)
        self.assertEqual(group.slots_left, 0)

    def test_eleventh_player_is_refused(self):
        group = self.make_group()
        for index in range(MAX_GROUP_PLAYERS - 1):
            post_json(self.owner_client, '/api/create_bettor', {
                'username': f'p{index}', 'password': 'PlayerPass123!', 'balance': 100,
            })
        response = post_json(self.owner_client, '/api/create_bettor', {
            'username': 'one_too_many', 'password': 'PlayerPass123!', 'balance': 100,
        })
        self.assertFalse(response.json()['ok'])
        self.assertIn('maximum', response.json()['error'])
        self.assertFalse(BettorAccount.objects.filter(username='one_too_many').exists())
        self.assertEqual(group.player_count, MAX_GROUP_PLAYERS)

    def test_freed_slot_can_be_reused(self):
        group = self.make_group()
        created = []
        for index in range(MAX_GROUP_PLAYERS - 1):
            post_json(self.owner_client, '/api/create_bettor', {
                'username': f'p{index}', 'password': 'PlayerPass123!', 'balance': 100,
            })
            created.append(BettorAccount.objects.get(username=f'p{index}'))
        post_json(self.owner_client, '/api/delete_bettor', {'id': created[0].pk})
        self.assertFalse(group.is_full)
        response = post_json(self.owner_client, '/api/create_bettor', {
            'username': 'replacement', 'password': 'PlayerPass123!', 'balance': 100,
        })
        self.assertTrue(response.json()['ok'], response.content)

    # --- owner scoping ---------------------------------------------------
    def test_owner_sees_only_their_own_players(self):
        self.make_group('Shop A', self.owner)
        self.make_group('Shop B', self.rival)
        post_json(self.owner_client, '/api/create_bettor', {
            'username': 'mine', 'password': 'PlayerPass123!', 'balance': 100,
        })
        rival_client = Client()
        rival_client.force_login(self.rival)
        post_json(rival_client, '/api/create_bettor', {
            'username': 'theirs', 'password': 'PlayerPass123!', 'balance': 100,
        })
        names = [a['username'] for a in self.owner_client.get('/api/list_bettors').json()['accounts']]
        self.assertIn('mine', names)
        self.assertNotIn('theirs', names)
        self.assertNotIn(self.rival.username, names)

    def test_owner_cannot_edit_or_delete_another_groups_player(self):
        self.make_group('Shop A', self.owner)
        self.make_group('Shop B', self.rival)
        rival_client = Client()
        rival_client.force_login(self.rival)
        post_json(rival_client, '/api/create_bettor', {
            'username': 'theirs', 'password': 'PlayerPass123!', 'balance': 100,
        })
        theirs = BettorAccount.objects.get(username='theirs')
        edit = post_json(self.owner_client, '/api/edit_bettor', {'id': theirs.pk, 'balance': 999999})
        self.assertFalse(edit.json()['ok'])
        delete = post_json(self.owner_client, '/api/delete_bettor', {'id': theirs.pk})
        self.assertFalse(delete.json()['ok'])
        theirs.refresh_from_db()
        self.assertEqual(theirs.balance, 100)

    def test_owner_cannot_move_a_player_between_groups(self):
        group = self.make_group('Shop A', self.owner)
        post_json(self.owner_client, '/api/create_bettor', {
            'username': 'mine', 'password': 'PlayerPass123!', 'balance': 100,
        })
        mine = BettorAccount.objects.get(username='mine')
        response = post_json(self.owner_client, '/api/edit_bettor', {'id': mine.pk, 'group_id': None})
        self.assertFalse(response.json()['ok'])
        mine.refresh_from_db()
        self.assertEqual(mine.group, group)

    def test_owner_cannot_create_a_player_into_another_group(self):
        self.make_group('Shop A', self.owner)
        other = self.make_group('Shop B', self.rival)
        response = post_json(self.owner_client, '/api/create_bettor', {
            'username': 'sneaky', 'password': 'PlayerPass123!', 'balance': 100,
            'group_id': other.pk,
        })
        self.assertFalse(response.json()['ok'])
        self.assertFalse(BettorAccount.objects.filter(username='sneaky').exists())

    def test_superuser_sees_every_player(self):
        self.make_group('Shop A', self.owner)
        self.make_group('Shop B', self.rival)
        names = [a['username'] for a in self.admin_client.get('/api/list_bettors').json()['accounts']]
        self.assertIn(self.owner.username, names)
        self.assertIn(self.rival.username, names)

    # --- owner protection of their own row -------------------------------
    def test_owner_cannot_delete_or_edit_their_own_owner_player_row(self):
        group = self.make_group()
        own = group.owner_player
        delete = post_json(self.owner_client, '/api/delete_bettor', {'id': own.pk})
        self.assertFalse(delete.json()['ok'])
        edit = post_json(self.owner_client, '/api/edit_bettor', {'id': own.pk, 'balance': 5})
        self.assertFalse(edit.json()['ok'])
        own.refresh_from_db()
        self.assertTrue(BettorAccount.objects.filter(pk=own.pk).exists())

    def test_superuser_can_delete_a_group_owner_player_row(self):
        group = self.make_group()
        response = post_json(self.admin_client, '/api/delete_bettor', {'id': group.owner_player.pk})
        self.assertTrue(response.json()['ok'], response.content)

    # --- dual role -------------------------------------------------------
    def test_owner_bets_as_their_own_player_login(self):
        group = self.make_group()
        profile = self.owner_client.get('/api/bettor_profile')
        self.assertTrue(profile.json()['ok'], profile.content)
        self.assertEqual(profile.json()['account']['id'], group.owner_player.pk)
        self.assertTrue(profile.json()['account']['is_group_owner'])

    def test_owner_without_a_group_has_no_player_identity(self):
        response = self.owner_client.get('/api/bettor_profile')
        self.assertFalse(response.json()['ok'])

    def test_owner_player_password_cannot_sign_in_at_player_login(self):
        group = self.make_group()
        response = post_json(Client(), '/api/bettor_login', {
            'username': group.owner_player.username, 'password': 'guess',
        })
        self.assertFalse(response.json()['ok'])

    def test_owner_sees_the_limit_alarm_for_their_own_player_login(self):
        group = self.make_group()
        group.owner_player.hot_limits = {'23': 75000}
        group.owner_player.save()
        response = self.owner_client.get('/bet/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['bettor_account']['id'], group.owner_player.pk)
        self.assertEqual([item['num'] for item in response.context['bettor_hot_limits']], ['23'])

    # --- access gate -----------------------------------------------------
    def test_owner_with_group_reaches_the_control_center(self):
        self.make_group()
        response = self.owner_client.get('/app/admin/')
        self.assertEqual(response.status_code, 200)

    def test_owner_without_group_is_redirected_from_control_center(self):
        response = self.owner_client.get('/app/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_owner_without_group_cannot_list_players(self):
        self.assertEqual(self.owner_client.get('/api/list_bettors').status_code, 403)

    def test_bootstrap_reports_player_management_flag(self):
        self.make_group()
        body = self.owner_client.get('/app/admin/').content.decode()
        self.assertIn('"canManagePlayers": true', body)
        self.assertIn('"admin": false', body)
        self.assertIn('"canManagePlayers": true', self.admin_client.get('/app/admin/').content.decode())

    def test_owner_lists_only_their_own_group(self):
        self.make_group('Shop A', self.owner)
        self.make_group('Shop B', self.rival)
        names = [g['name'] for g in self.owner_client.get('/api/list_groups').json()['groups']]
        self.assertEqual(names, ['Shop A'])
        all_names = [g['name'] for g in self.admin_client.get('/api/list_groups').json()['groups']]
        self.assertEqual(sorted(all_names), ['Shop A', 'Shop B'])

    def test_group_listing_is_open_to_any_group_owner(self):
        self.make_group()
        response = self.owner_client.get('/api/list_groups')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

    # --- group deletion --------------------------------------------------
    def test_deleting_a_group_releases_its_players_instead_of_cascading(self):
        group = self.make_group()
        post_json(self.owner_client, '/api/create_bettor', {
            'username': 'mine', 'password': 'PlayerPass123!', 'balance': 700,
        })
        mine = BettorAccount.objects.get(username='mine')
        response = post_json(self.admin_client, '/api/delete_group', {'id': group.pk})
        self.assertTrue(response.json()['ok'], response.content)
        self.assertFalse(PlayerGroup.objects.filter(pk=group.pk).exists())
        mine.refresh_from_db()
        self.assertIsNone(mine.group)
        self.assertEqual(mine.balance, 700)

    def test_owner_with_a_group_cannot_be_deleted_until_the_group_is_gone(self):
        group = self.make_group()
        response = post_json(self.admin_client, '/api/delete_operator', {'id': self.owner.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['ok'])
        self.assertIn(group.name, response.json()['error'])
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        # Clearing the way lets the delete through.
        self.assertTrue(post_json(self.admin_client, '/api/delete_group', {'id': group.pk}).json()['ok'])
        self.assertTrue(post_json(self.admin_client, '/api/delete_operator', {'id': self.owner.pk}).json()['ok'])
        self.assertFalse(User.objects.filter(pk=self.owner.pk).exists())

    def test_suspending_a_group_owner_closes_their_player_access(self):
        self.make_group()
        post_json(self.admin_client, '/api/edit_operator', {'id': self.owner.pk, 'is_active': False})
        # A fresh client has to sign in again, and the suspended owner cannot.
        blocked = Client()
        blocked.login(username='shopowner', password='OwnerPass123!')
        self.assertEqual(blocked.get('/api/list_bettors').status_code, 403)
        self.assertEqual(blocked.get('/app/admin/').status_code, 302)

    def test_suspending_the_owner_player_row_closes_the_dual_role(self):
        group = self.make_group()
        post_json(self.admin_client, '/api/edit_bettor', {'id': group.owner_player.pk, 'is_active': False})
        profile = self.owner_client.get('/api/bettor_profile')
        self.assertFalse(profile.json()['ok'])
        settings = self.owner_client.get('/bet/settings/')
        self.assertIsNone(settings.context['bettor_account'])

    def test_bad_ids_do_not_crash_the_endpoints(self):
        self.make_group()
        for path, payload in (
            ('/api/edit_bettor', {'id': 'not-a-number'}),
            ('/api/delete_bettor', {'id': 'not-a-number'}),
            ('/api/create_bettor', {'username': 'x1', 'password': 'PlayerPass123!', 'group_id': 'not-a-number'}),
            ('/api/edit_group', {'id': 'not-a-number'}),
            ('/api/delete_group', {'id': 'not-a-number'}),
        ):
            response = post_json(self.admin_client, path, payload)
            self.assertEqual(response.status_code, 200, f'{path} returned {response.status_code}')
            self.assertFalse(response.json()['ok'], f'{path} should reject a non-numeric id')
