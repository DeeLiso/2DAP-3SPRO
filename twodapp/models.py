from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password

# A player group is one shop owner plus the player logins they manage. The cap
# counts every member, including the owner's own player login, so the number a
# shop owner sees in the UI is the number of logins that can actually sign in.
MAX_GROUP_PLAYERS = 10


class GameState(models.Model):
    """Single-row table holding the global ledger state."""
    slug = models.SlugField(unique=True, default='main')
    ledger = models.JSONField(default=list)  # list of 100 integers
    specific_limits = models.JSONField(default=dict)  # e.g. {'05': 30000}
    global_limit = models.IntegerField(default=50000)
    total_amount = models.BigIntegerField(default=0)
    valid_lines = models.IntegerField(default=0)
    bettor_name = models.CharField(max_length=100, blank=True, default='')
    bettor_date = models.CharField(max_length=10, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Game State'

    def save(self, *args, **kwargs):
        if not isinstance(self.ledger, list) or len(self.ledger) != 100:
            self.ledger = [0] * 100
        if not isinstance(self.specific_limits, dict):
            self.specific_limits = {}
        super().save(*args, **kwargs)

    @classmethod
    def get_state(cls):
        obj, _ = cls.objects.get_or_create(slug='main', defaults={'ledger': [0] * 100})
        if len(obj.ledger) != 100:
            obj.ledger = [0] * 100
            obj.save()
        return obj


class BettorAccount(models.Model):
    username = models.CharField(max_length=50, unique=True)
    password_hash = models.CharField(max_length=128)
    phone = models.CharField(max_length=20, blank=True, default='')
    balance = models.IntegerField(default=0)
    hot_limits = models.JSONField(default=dict)  # e.g. {'23': 5000, '44': 3000}
    multiplier = models.IntegerField(default=80)  # odds, e.g. 80 or 85
    is_active = models.BooleanField(default=True)
    group = models.ForeignKey('PlayerGroup', on_delete=models.SET_NULL, null=True, blank=True, related_name='players')
    last_user_agent = models.CharField(max_length=300, blank=True, default='')
    last_ip = models.CharField(max_length=50, blank=True, default='')
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw):
        self.password_hash = make_password(raw)

    def check_password(self, raw):
        return check_password(raw, self.password_hash)

    @property
    def is_group_owner_player(self):
        return bool(self.group_id and self.group.owner_player_id == self.pk)

    def to_dict(self):
        from django.utils import timezone as tz
        return {
            'id': self.pk,
            'username': self.username,
            'phone': self.phone,
            'balance': self.balance,
            'hot_limits': self.hot_limits,
            'multiplier': self.multiplier,
            'is_active': self.is_active,
            'group_id': self.group_id,
            'group_name': self.group.name if self.group_id else '',
            'is_group_owner': self.is_group_owner_player,
            'last_user_agent': self.last_user_agent,
            'last_ip': self.last_ip,
            'last_seen': tz.localtime(self.last_seen).strftime('%Y-%m-%d %H:%M') if self.last_seen else '',
        }


class PlayerGroup(models.Model):
    """A shop owner and the player logins under that owner.

    The owner is a normal Django user. `owner_player` is the owner's own
    player login, so one person can run the shop and bet at the same time
    without a second set of credentials.
    """

    name = models.CharField(max_length=100, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='player_groups')
    owner_player = models.OneToOneField(
        'BettorAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owning_group',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Player Group'

    @property
    def player_count(self):
        return self.players.count()

    @property
    def slots_left(self):
        return max(MAX_GROUP_PLAYERS - self.player_count, 0)

    @property
    def is_full(self):
        return self.player_count >= MAX_GROUP_PLAYERS

    def to_dict(self):
        return {
            'id': self.pk,
            'name': self.name,
            'owner_username': self.owner.username,
            'owner_player_id': self.owner_player_id,
            'player_count': self.player_count,
            'slots_left': self.slots_left,
            'max_players': MAX_GROUP_PLAYERS,
            'created_at': timezone.localtime(self.created_at).strftime('%Y-%m-%d') if self.created_at else '',
        }


class OperationLog(models.Model):
    formula = models.CharField(max_length=50, blank=True, default='')
    original = models.TextField(default='')
    numbers = models.JSONField(default=list, blank=True)  # generated numbers list
    count = models.IntegerField(default=0)
    amount = models.IntegerField(default=0)
    is_error = models.BooleanField(default=False)
    is_canceled = models.BooleanField(default=False)
    bettor_name = models.CharField(max_length=100, blank=True, default='')
    bettor_date = models.CharField(max_length=10, blank=True, default='')
    bettor_username = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']


class ArchivedLog(models.Model):
    """Records moved to the Local Store when Clear Data is used."""
    formula = models.CharField(max_length=50, blank=True, default='')
    original = models.TextField(default='')
    numbers = models.JSONField(default=list, blank=True)
    count = models.IntegerField(default=0)
    amount = models.IntegerField(default=0)
    is_error = models.BooleanField(default=False)
    is_canceled = models.BooleanField(default=False)
    bettor_name = models.CharField(max_length=100, blank=True, default='')
    bettor_date = models.CharField(max_length=10, blank=True, default='')
    bettor_username = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-archived_at']


class ChatMessage(models.Model):
    sender_type = models.CharField(max_length=10)  # 'owner' or 'player'
    sender_name = models.CharField(max_length=50)
    message = models.TextField(blank=True, default='')
    photo = models.ImageField(upload_to='chat_photos/', blank=True, null=True)
    audio = models.FileField(upload_to='chat_voice/', blank=True, null=True)
    is_pinned = models.BooleanField(default=False)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    is_deleted = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']


class ChatPresence(models.Model):
    user_type = models.CharField(max_length=10)  # 'owner' or 'player'
    user_name = models.CharField(max_length=50)
    last_seen = models.DateTimeField(auto_now=True)
    is_typing = models.BooleanField(default=False)

    class Meta:
        unique_together = [('user_type', 'user_name')]


class ChatReaction(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='reactions')
    emoji = models.CharField(max_length=10)
    user_type = models.CharField(max_length=10)  # 'owner' or 'player'
    user_name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class ControlCenterAudit(models.Model):
    """Every account change made from the Admin Control Center."""
    actor_id = models.IntegerField(null=True, blank=True)
    actor_name = models.CharField(max_length=150, blank=True, default='')
    action = models.CharField(max_length=40)  # create / update / suspend / activate / reset_password / delete
    target_type = models.CharField(max_length=20)  # 'owner' or 'player'
    target_id = models.IntegerField(null=True, blank=True)
    target_name = models.CharField(max_length=150, blank=True, default='')
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name = 'Control Center Audit'
        verbose_name_plural = 'Control Center Audit'


def log_audit(request, action, target_type, target, changes=None):
    """Record a Control Center account change. Never raises."""
    user = getattr(request, 'user', None)
    try:
        ControlCenterAudit.objects.create(
            actor_id=user.pk if user is not None and user.is_authenticated else None,
            actor_name=(user.get_username() if user is not None and user.is_authenticated else '') or 'system',
            action=action,
            target_type=target_type,
            target_id=getattr(target, 'pk', None),
            target_name=str(
                getattr(target, 'username', '')
                or getattr(target, 'name', '')
                or ''
            )[:150],
            changes=changes or {},
        )
    except Exception:
        pass
