import functools
import json
import csv
import secrets
import urllib.request
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import (GameState, OperationLog, ArchivedLog, BettorAccount,
                     ChatMessage, ChatPresence, ChatReaction, ControlCenterAudit,
                     PlayerGroup, MAX_GROUP_PLAYERS, log_audit)
from .parser import parse_text

MMT = ZoneInfo('Asia/Yangon')


def robots_txt(request):
    return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain')


def api_login_required(fn):
    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated and not request.session.get('bettor_account_id'):
            return JsonResponse({'ok': False, 'error': 'Not authenticated'}, status=403)
        return fn(request, *args, **kwargs)
    return wrapper


def api_superuser_required(fn):
    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_active or not request.user.is_superuser:
            return JsonResponse({'ok': False, 'error': 'Superuser access required'}, status=403)
        return fn(request, *args, **kwargs)
    return wrapper


def _can_manage_players(user):
    """True for Admin Only (CP) and for shop owners who own a player group.

    A shop owner is an ordinary Django user, so `is_superuser` is the wrong
    test: they manage the players in their own group and nothing else.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return PlayerGroup.objects.filter(owner=user).exists()


def api_player_manager_required(fn):
    @functools.wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not _can_manage_players(request.user):
            return JsonResponse({'ok': False, 'error': 'Player management access required'}, status=403)
        return fn(request, *args, **kwargs)
    return wrapper


def _owned_group(user):
    """The caller's own player group, or None for a superuser / non-owner."""
    if not user or not user.is_authenticated or not user.is_active or user.is_superuser:
        return None
    return PlayerGroup.objects.filter(owner=user).first()


def _scoped_bettors(user):
    """Bettor rows the caller is allowed to read or change.

    Superusers see every login. A shop owner sees only the logins in their own
    group, which is what keeps one shop from touching another's balances.
    """
    if user.is_superuser:
        return BettorAccount.objects.all()
    group = _owned_group(user)
    return BettorAccount.objects.filter(group=group) if group else BettorAccount.objects.none()


def _group_for_new_bettor(user):
    """Pick the group a newly created player should land in."""
    if user.is_superuser:
        return None
    return _owned_group(user)


def _resolve_bettor(request):
    """The BettorAccount acting on this request, or None.

    A shop owner who also holds the player role has no separate player session:
    they sign in as a Django user, and their group's owner_player is the login
    their bets and balance are recorded against.
    """
    acc_id = request.session.get('bettor_account_id')
    if acc_id:
        return BettorAccount.objects.filter(pk=acc_id).first()
    user = request.user
    if user and user.is_authenticated and user.is_active:
        owner_player = PlayerGroup.objects.filter(owner=user).exclude(owner_player=None).values_list('owner_player_id', flat=True).first()
        if owner_player:
            # Honour is_active, so suspending the owner's player row closes the
            # dual role the same way it closes a normal player sign-in.
            return BettorAccount.objects.filter(pk=owner_player, is_active=True).first()
    return None


def logout_view(request):
    logout(request)
    return redirect('login')


def _revoke_sessions(*, bettor_account_id=None, user_id=None):
    """Drop every session that authenticates as a bettor account or a Django user.

    Without this, suspending or deleting an account leaves an already-issued
    session working until it expires.
    """
    if bettor_account_id is None and user_id is None:
        return 0
    target_bettor = str(bettor_account_id) if bettor_account_id is not None else None
    target_user = str(user_id) if user_id is not None else None
    # SessionBase.decode is an instance method, not a classmethod, so it has to
    # be reached through an instance. Calling it on the class raises TypeError
    # and silently matches nothing.
    decoder = SessionStore()
    stale = []
    for session_key, session_data in Session.objects.values_list('session_key', 'session_data'):
        try:
            data = decoder.decode(session_data)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if target_bettor is not None and str(data.get('bettor_account_id') or '') == target_bettor:
            stale.append(session_key)
        elif target_user is not None and str(data.get('_auth_user_id') or '') == target_user:
            stale.append(session_key)
    if stale:
        Session.objects.filter(session_key__in=stale).delete()
    return len(stale)


def _serialize_log(log):
    return {
        'id': log.pk,
        'formula': log.formula,
        'original': log.original,
        'numbers': log.numbers,
        'count': log.count,
        'amount': log.amount,
        'is_error': log.is_error,
        'is_canceled': log.is_canceled,
        'bettor_name': log.bettor_name,
        'bettor_date': log.bettor_date,
        'bettor_username': log.bettor_username,
        'time': log.created_at.astimezone(MMT).strftime('%Y-%m-%d %H:%M:%S'),
    }


def over_limit_items(state):
    bettors_by_num = {}
    for name, nums in OperationLog.objects.exclude(bettor_name='').values_list('bettor_name', 'numbers'):
        for n in nums or []:
            bettors_by_num.setdefault(n, set()).add(name)
    items = []
    for i, amt in enumerate(state.ledger):
        num = f'{i:02d}'
        limit = state.specific_limits.get(num) or state.global_limit
        if limit and amt >= limit:
            items.append({
                'num': num, 'amount': amt, 'limit': limit, 'over': amt - limit,
                'bettors': sorted(bettors_by_num.get(num, set()))[:3],
            })
    return items


@login_required
def records_page(request):
    state = GameState.get_state()
    records = [_serialize_log(l) for l in OperationLog.objects.order_by('-id')[:1000]]
    return render(request, 'twodapp/records.html', {
        'records_json': json.dumps(records),
        'count': len(records),
        'over_limits_json': json.dumps(over_limit_items(state)),
    })


@api_login_required
def bettor_records_page(request):
    bettor_username = request.session.get('bettor_username', '')
    state = GameState.get_state()
    logs = OperationLog.objects.filter(bettor_username=bettor_username).order_by('-id')[:500] if bettor_username else []
    records = [_serialize_log(l) for l in logs]
    return render(request, 'twodapp/bettor_records.html', {
        'records_json': json.dumps(records),
        'count': len(records),
        'bettor_name': bettor_username,
    })


@login_required
def limit_page(request):
    state = GameState.get_state()
    over = over_limit_items(state)
    over_map = {o['num']: o for o in over}
    logs = []
    for l in OperationLog.objects.order_by('-id')[:2000]:
        if l.is_error:
            continue
        hit = [n for n in (l.numbers or []) if n in over_map]
        if not hit:
            continue
        logs.append({
            'id': l.pk,
            'formula': l.formula,
            'original': l.original,
            'numbers': l.numbers or [],
            'amount': l.amount,
            'bettor_name': l.bettor_name,
            'time': l.created_at.astimezone(MMT).strftime('%Y-%m-%d %H:%M:%S'),
            'over_nums': hit,
            'over_detail': [over_map[n] for n in hit],
        })
    return render(request, 'twodapp/limit.html', {
        'over_limits_json': json.dumps(over),
        'logs_json': json.dumps(logs),
        'count': len(logs),
    })


@login_required
def ledger_page(request):
    state = GameState.get_state()
    return render(request, 'twodapp/ledger.html', {
        'ledger_json': json.dumps(state.ledger),
        'specific_limits_json': json.dumps(state.specific_limits),
        'global_limit': state.global_limit,
        'total_amount': state.total_amount,
        'valid_lines': state.valid_lines,
    })


def state_payload(state):
    over = 0
    for i, amt in enumerate(state.ledger):
        num = f'{i:02d}'
        limit = state.specific_limits.get(num) or state.global_limit
        if amt >= limit:
            over += 1
    return {
        'ledger': state.ledger,
        'global_limit': state.global_limit,
        'specific_limits': state.specific_limits,
        'total_amount': state.total_amount,
        'valid_lines': state.valid_lines,
        'over_limit': over,
    }


@login_required
def home_page(request):
    return render(request, 'twodapp/home.html')


def index(request):
    state = GameState.get_state()
    records = [_serialize_log(l) for l in OperationLog.objects.order_by('-id')[:200]]
    user_type = request.GET.get('type', 'dealer')
    return render(request, 'twodapp/index.html', {
        'ledger_json': json.dumps(state.ledger),
        'specific_limits_json': json.dumps(state.specific_limits),
        'global_limit': state.global_limit,
        'total_amount': state.total_amount,
        'valid_lines': state.valid_lines,
        'bettor_name': state.bettor_name,
        'bettor_date': state.bettor_date,
        'logs_json': json.dumps(records),
        'over_limits_json': json.dumps(over_limit_items(state)),
        'user_type': user_type,
        'bettor_username': request.session.get('bettor_username', ''),
    })


def _json_body(request):
    try:
        data = json.loads(request.body or b'{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _bool_value(value, default=False):
    """Strict boolean parse.

    Raises ValueError for anything that is not an unambiguous boolean, so a
    typo in a payload is reported instead of being silently read as False.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {'1', 'true', 'yes', 'on'}:
            return True
        if token in {'0', 'false', 'no', 'off'}:
            return False
    raise ValueError(f'Expected a boolean, got {value!r}')


def _read_flags(data, keys, target):
    """Apply strict boolean flags from a payload onto a model instance."""
    for key, attr in keys:
        if key in data:
            setattr(target, attr, _bool_value(data.get(key), getattr(target, attr)))


def _flag_bool(value, default):
    """Non-raising _bool_value, for comparisons that must not fail the request."""
    try:
        return _bool_value(value, default)
    except ValueError:
        return default


def _flag_error(error):
    return JsonResponse({'ok': False, 'error': f'Invalid boolean flag ({error})'})


ALLOWED_MULTIPLIERS = (80, 85)


def _multiplier_value(value, default=80):
    try:
        parsed = int(str(value).strip().lower().rstrip('x'))
    except (TypeError, ValueError):
        return default
    return parsed if parsed in ALLOWED_MULTIPLIERS else default


MAX_BALANCE = 2147483647


def _clean_balance(value):
    """Return a validated balance, or None when the value is not usable."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= MAX_BALANCE else None


def _last_superuser_guard(user, new_is_superuser, new_is_active):
    """Refuse a change that would leave no usable superuser behind."""
    if not user.is_superuser or not user.is_active:
        return ''
    if new_is_superuser and new_is_active:
        return ''
    remaining = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).count()
    if remaining == 0:
        return 'At least one active superuser must remain.'
    return ''


def _validate_new_password(password, user=None):
    """Return an error string when the password fails the configured policy."""
    from django.contrib.auth.password_validation import validate_password
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return ' '.join(exc.messages)
    return ''


def _clean_hot_limits(raw):
    """Normalize a hot_limits payload to {'05': 5000}, or None when invalid.

    Accepts {5: '5000'} and {'05': 5000} alike so that the React sheet and the
    legacy pages agree on the stored key format.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        return None
    cleaned = {}
    for key, value in raw.items():
        number = str(key).strip()
        if not number.isdigit() or len(number) > 2:
            return None
        index = int(number)
        if not 0 <= index <= 99:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            amount = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if not 0 <= amount <= MAX_BALANCE:
            return None
        key = f'{index:02d}'
        # {'05': 1, '5': 2} collapses to the same slot; refuse instead of
        # silently keeping whichever pair happened to be last.
        if key in cleaned:
            return None
        cleaned[key] = amount
    return cleaned


def react_bootstrap(request, screen):
    user = request.user
    display_name = (user.get_full_name() or user.username or 'Guest') if user.is_authenticated else ''
    return {
        'screen': screen,
        'csrfToken': get_token(request),
        'appVersion': getattr(settings, 'APP_VERSION', '1.0.0'),
        'user': {
            'id': user.pk if user.is_authenticated else None,
            'username': user.username if user.is_authenticated else '',
            'displayName': display_name if user.is_authenticated else '',
            'isAuthenticated': user.is_authenticated,
            'isSuperuser': user.is_authenticated and user.is_active and user.is_superuser,
            'isStaff': user.is_authenticated and user.is_active and user.is_staff,
        },
        'roleFlags': {
            'ownerAuthenticated': user.is_authenticated and user.is_active,
            'admin': user.is_authenticated and user.is_active and user.is_superuser,
            'canManagePlayers': _can_manage_players(user),
            'playerAuthenticated': bool(request.session.get('bettor_account_id')),
        },
        'routes': {
            'gateway': reverse('react_gateway'),
            'admin': reverse('react_admin'),
            'login': reverse('login'),
            'ownerApp': '/bet/?type=dealer',
            'playerLogin': reverse('bettor_login'),
        },
    }


def _safe_next(request, candidate, fallback='/app/'):
    target = (candidate or '').strip()
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return fallback


@require_http_methods(['GET', 'POST'])
def react_login(request):
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        next_path = _safe_next(request, request.POST.get('next'), reverse('react_gateway'))
        if not username or not password:
            return JsonResponse({'ok': False, 'error': 'Username and password are required.'}, status=400)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return JsonResponse({'ok': False, 'error': 'Invalid credentials. Please try again.'}, status=400)
        if not user.is_active:
            return JsonResponse({'ok': False, 'error': 'This account is suspended. Contact an administrator.'}, status=403)
        login(request, user)
        response = JsonResponse({'ok': True, 'redirect': next_path})
        response['Content-Security-Policy'] = "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'"
        return response

    next_path = _safe_next(request, request.GET.get('next'), reverse('react_gateway'))
    bootstrap = {
        'screen': 'login',
        'csrfToken': get_token(request),
        'appVersion': getattr(settings, 'APP_VERSION', '1.0.0'),
        'user': {
            'id': None,
            'username': '',
            'displayName': '',
            'isAuthenticated': False,
            'isSuperuser': False,
            'isStaff': False,
        },
        'roleFlags': {
            'ownerAuthenticated': False,
            'admin': False,
            'playerAuthenticated': False,
        },
        'routes': {
            'gateway': reverse('react_gateway'),
            'admin': reverse('react_admin'),
            'login': reverse('login'),
            'ownerApp': '/bet/?type=dealer',
            'playerLogin': reverse('bettor_login'),
        },
        'nextPath': next_path,
    }
    response = render(request, 'twodapp/react_app.html', {'bootstrap': bootstrap})
    response['Content-Security-Policy'] = "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'"
    return response


@require_GET
def react_app(request, screen='gateway'):
    if screen == 'admin' and not _can_manage_players(request.user):
        return redirect_to_login(request.get_full_path(), resolve_url('login'))
    response = render(request, 'twodapp/react_app.html', {'bootstrap': react_bootstrap(request, screen)})
    response['Content-Security-Policy'] = "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'"
    return response


@require_GET
@api_login_required
def api_live(request):
    """Proxy the Thai Stock 2D live API to avoid CORS issues."""
    try:
        req = urllib.request.Request(
            'https://api.thaistock2d.com/live',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        live = data.get('live', {})
        result = data.get('result', [])
        return JsonResponse({
            'ok': True,
            'result': live.get('twod', '--'),
            'set': live.get('set', '--'),
            'value': live.get('value', '--'),
            'time': live.get('time', ''),
            'today_results': [
                {
                    'time': r.get('open_time', ''),
                    'result': r.get('twod', '--'),
                    'set': r.get('set', '--'),
                    'value': r.get('value', '--'),
                }
                for r in result
            ],
            'holiday': data.get('holiday', {}),
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


@require_POST
@api_login_required
def api_parse(request):
    text = request.POST.get('text', '')
    action = request.POST.get('action', 'add')  # 'add' or 'delete'
    bettor_name = request.POST.get('bettor_name', '').strip()
    bettor_date = request.POST.get('bettor_date', '').strip()
    bettor_username = request.session.get('bettor_username', '')
    state = GameState.get_state()
    parsed, errors = parse_text(text)
    log_entries = []

    ledger = list(state.ledger)
    for r in parsed:
        for num in r['numbers']:
            idx = int(num)
            if 0 <= idx < 100:
                if action == 'delete':
                    ledger[idx] = max(0, ledger[idx] - r['amount'])
                    state.total_amount = max(0, state.total_amount - r['amount'])
                else:
                    ledger[idx] += r['amount']
                    state.total_amount += r['amount']
        state.valid_lines += 1
        log = OperationLog.objects.create(
            formula=r['formula'], original=r['original'],
            numbers=r['numbers'], count=r['count'], amount=r['amount'],
            bettor_name=bettor_name, bettor_date=bettor_date,
            bettor_username=bettor_username,
        )
        log_entries.append(_serialize_log(log))

    for err in errors:
        log = OperationLog.objects.create(original=err, is_error=True)
        log_entries.append(_serialize_log(log))

    state.ledger = ledger
    state.save()
    return JsonResponse({'ok': True, 'logs': log_entries, **state_payload(state)})


@require_POST
@api_login_required
def api_set_global_limit(request):
    try:
        val = int(request.POST.get('limit', ''))
    except ValueError:
        val = 0
    if val > 0:
        state = GameState.get_state()
        state.global_limit = val
        state.save()
        return JsonResponse({'ok': True, **state_payload(state)})
    return JsonResponse({'ok': False, 'error': 'Invalid limit'})


@require_POST
@api_login_required
def api_delete_logs(request):
    ids_raw = request.POST.get('ids', '')
    state = GameState.get_state()
    ledger = list(state.ledger)
    try:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    except ValueError:
        ids = []
    if not ids:
        return JsonResponse({'ok': False, 'error': 'Invalid ids'})
    for log in OperationLog.objects.filter(pk__in=ids):
        for num in log.numbers or []:
            try:
                idx = int(num)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < 100:
                ledger[idx] = max(0, ledger[idx] - log.amount)
                state.total_amount = max(0, state.total_amount - log.amount)
    state.ledger = ledger
    state.valid_lines = max(0, state.valid_lines - OperationLog.objects.filter(pk__in=ids, is_error=False).count())
    state.save()
    OperationLog.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_toggle_cancel(request):
    """Cancel or restore one or more records, adjusting the ledger accordingly.
    Expects 'ids' (comma-separated) and 'canceled' (true/false).
    """
    ids_raw = request.POST.get('ids', '')
    canceled = request.POST.get('canceled', 'true').lower() == 'true'
    ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
    if not ids:
        return JsonResponse({'ok': False, 'error': 'Invalid ids'})

    state = GameState.get_state()
    ledger = list(state.ledger)
    for log in OperationLog.objects.filter(pk__in=ids):
        if canceled == log.is_canceled:
            continue
        sign = -1 if canceled else 1
        for num in log.numbers or []:
            try:
                idx = int(num)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < 100:
                ledger[idx] = max(0, ledger[idx] + sign * log.amount)
                state.total_amount = max(0, state.total_amount + sign * log.amount)
        log.is_canceled = canceled
        log.save()
    state.ledger = ledger
    state.save()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_edit_logs(request):
    """Edit amounts for multiple records at once.
    Expects 'items' = JSON list of {"id": <int>, "amount": <int>}.
    """
    import json as _json
    try:
        items = _json.loads(request.POST.get('items', '[]'))
    except (ValueError, TypeError):
        items = []
    if not items:
        return JsonResponse({'ok': False, 'error': 'No items'})

    state = GameState.get_state()
    ledger = list(state.ledger)
    updates = []
    for it in items:
        try:
            log_id = int(it.get('id'))
            new_amount = int(it.get('amount'))
        except (ValueError, TypeError):
            continue
        if new_amount <= 0:
            continue
        updates.append((log_id, new_amount))

    logs = OperationLog.objects.filter(pk__in=[u[0] for u in updates])
    for log in logs:
        new_amount = dict(updates)[log.pk]
        diff = new_amount - log.amount
        if diff == 0:
            continue
        for num in log.numbers or []:
            try:
                idx = int(num)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < 100:
                ledger[idx] = max(0, ledger[idx] + diff)
                state.total_amount = max(0, state.total_amount + diff)
        log.amount = new_amount
        log.save()

    state.ledger = ledger
    state.save()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_set_specific_limit(request):
    num = request.POST.get('num', '').strip()
    num = num.zfill(2) if num.isdigit() else ''
    try:
        val = int(request.POST.get('limit', ''))
    except ValueError:
        val = 0

    state = GameState.get_state()
    if num and len(num) == 2 and 0 <= int(num) < 100:
        limits = dict(state.specific_limits)
        if val > 0:
            limits[num] = val
        else:
            limits.pop(num, None)
        state.specific_limits = limits
        state.save()
        return JsonResponse({'ok': True, **state_payload(state)})
    return JsonResponse({'ok': False, 'error': 'Invalid number'})


@require_POST
@api_login_required
def api_delete_specific_limit(request):
    num = request.POST.get('num', '').strip()
    state = GameState.get_state()
    limits = dict(state.specific_limits)
    limits.pop(num, None)
    state.specific_limits = limits
    state.save()
    return JsonResponse({'ok': True, **state_payload(state)})


@require_POST
@api_login_required
def api_save_meta(request):
    name = request.POST.get('name', '').strip()
    date = request.POST.get('date', '').strip()
    state = GameState.get_state()
    state.bettor_name = name
    state.bettor_date = date
    state.save()
    return JsonResponse({'ok': True, 'bettor_name': name, 'bettor_date': date})


@require_POST
@api_login_required
def api_clear_all(request):
    state = GameState.get_state()
    archived = [
        ArchivedLog(
            formula=l.formula, original=l.original, numbers=l.numbers, count=l.count,
            amount=l.amount, is_error=l.is_error, is_canceled=l.is_canceled,
            bettor_name=l.bettor_name, bettor_date=l.bettor_date,
            bettor_username=l.bettor_username, created_at=l.created_at,
        )
        for l in OperationLog.objects.all()
    ]
    ArchivedLog.objects.bulk_create(archived)
    state.ledger = [0] * 100
    state.specific_limits = {}
    state.total_amount = 0
    state.valid_lines = 0
    state.bettor_name = ''
    state.bettor_date = ''
    state.save()
    OperationLog.objects.all().delete()
    return JsonResponse({'ok': True, **state_payload(state)})


@login_required
def api_local_store_info(request):
    now = timezone.now()
    qs = ArchivedLog.objects.all()
    return JsonResponse({
        'ok': True,
        'total': qs.count(),
        'last_week': qs.filter(archived_at__gte=now - timedelta(days=7)).count(),
        'last_month': qs.filter(archived_at__gte=now - timedelta(days=30)).count(),
    })


@login_required
@require_POST
def api_local_store_delete(request):
    data = json.loads(request.body)
    period = data.get('period', '')
    now = timezone.now()
    if period == 'week':
        qs = ArchivedLog.objects.filter(archived_at__gte=now - timedelta(days=7))
    elif period == 'month':
        qs = ArchivedLog.objects.filter(archived_at__gte=now - timedelta(days=30))
    else:
        return JsonResponse({'ok': False, 'error': 'Invalid period'})
    count = qs.count()
    qs.delete()
    base = ArchivedLog.objects.all()
    return JsonResponse({
        'ok': True,
        'deleted': count,
        'total': base.count(),
        'last_week': base.filter(archived_at__gte=now - timedelta(days=7)).count(),
        'last_month': base.filter(archived_at__gte=now - timedelta(days=30)).count(),
    })


@login_required
def api_local_store_download(request):
    import io
    rows = ArchivedLog.objects.all().order_by('archived_at')
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['archived_at', 'created_at', 'formula', 'original', 'numbers', 'count',
                     'amount', 'is_error', 'is_canceled', 'bettor_name', 'bettor_date', 'bettor_username'])
    for l in rows:
        writer.writerow([
            l.archived_at.astimezone(MMT).strftime('%Y-%m-%d %H:%M:%S'),
            l.created_at.astimezone(MMT).strftime('%Y-%m-%d %H:%M:%S'),
            l.formula, l.original, json.dumps(l.numbers or []), l.count, l.amount,
            l.is_error, l.is_canceled, l.bettor_name, l.bettor_date, l.bettor_username,
        ])
    response = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="local_store_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    return response


@require_POST
@api_player_manager_required
def api_create_bettor(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    phone = (data.get('phone') or '').strip()
    balance = _clean_balance(data.get('balance', 0))
    if balance is None:
        return JsonResponse({'ok': False, 'error': 'Balance must be a whole number between 0 and 2147483647'})
    hot_limits = _clean_hot_limits(data.get('hot_limits'))
    if hot_limits is None:
        return JsonResponse({'ok': False, 'error': 'Hot limits must use 00-99:amount pairs'})

    if not username or not password:
        return JsonResponse({'ok': False, 'error': 'Username + password required'})
    password_error = _validate_new_password(password)
    if password_error:
        return JsonResponse({'ok': False, 'error': password_error})
    if BettorAccount.objects.filter(username=username).exists():
        return JsonResponse({'ok': False, 'error': f'"{username}" already exists'})

    # A shop owner can only add players to their own group, and only up to the
    # cap. Resolve the group before writing so a race cannot overshoot the cap.
    group = None
    group_id = data.get('group_id')
    if not request.user.is_superuser and group_id not in (None, ''):
        # Do not quietly drop the field: that would report success for a change
        # the caller is not allowed to make.
        return JsonResponse({'ok': False, 'error': 'Players are always added to your own group'})
    if request.user.is_superuser and group_id not in (None, ''):
        try:
            group = PlayerGroup.objects.get(pk=int(group_id))
        except (PlayerGroup.DoesNotExist, TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Group not found'})
    else:
        group = _group_for_new_bettor(request.user)
    if group is not None:
        if group.is_full:
            return JsonResponse({'ok': False, 'error': f'"{group.name}" already has the maximum of {MAX_GROUP_PLAYERS} players'})
    else:
        # No group resolved: either a superuser creating an ungrouped player, or
        # an owner without a group (already rejected by the decorator).
        if not request.user.is_superuser:
            return JsonResponse({'ok': False, 'error': 'You do not have a player group yet. Ask an administrator to create one.'})

    acc = BettorAccount(username=username, phone=phone, balance=balance, hot_limits=hot_limits,
                        multiplier=_multiplier_value(data.get('multiplier')), group=group)
    acc.set_password(password)
    try:
        acc.is_active = _bool_value(data.get('is_active'), True)
    except ValueError as exc:
        return _flag_error(exc)
    acc.save()
    log_audit(request, 'create', 'player', acc, {
        'username': acc.username, 'balance': acc.balance,
        'hot_limits': acc.hot_limits, 'is_active': acc.is_active,
        'group': acc.group.name if acc.group_id else '',
    })
    return JsonResponse({'ok': True, 'account': acc.to_dict()})


@api_player_manager_required
@require_GET
def api_list_bettors(request):
    accs = list(_scoped_bettors(request.user).order_by('-id').values(
        'id', 'username', 'phone', 'balance', 'hot_limits', 'multiplier', 'is_active', 'group_id',
        'last_user_agent', 'last_ip', 'last_seen'
    ))
    for a in accs:
        if a.get('last_seen'):
            a['last_seen'] = a['last_seen'].strftime('%Y-%m-%d %H:%M')
    return JsonResponse({'ok': True, 'accounts': accs})


@require_POST
@api_player_manager_required
def api_delete_bettor(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    try:
        acc = _scoped_bettors(request.user).get(pk=data.get('id'))
    except (BettorAccount.DoesNotExist, TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Account not found'})
    # An owner's own player login is their balance and bet history. Removing it
    # would silently break their dual role, so it is protected the same way the
    # UI already protects an owner from deleting themselves. A superuser can
    # still remove it, because that is the escape hatch for a lost owner row.
    if acc.is_group_owner_player and not request.user.is_superuser:
        return JsonResponse({'ok': False, 'error': 'You cannot delete your own owner player login. Delete the group instead.'})
    username, was_active = acc.username, acc.is_active
    revoked = _revoke_sessions(bettor_account_id=acc.pk)
    acc.delete()
    log_audit(request, 'delete', 'player', None, {
        'username': username, 'was_active': was_active, 'sessions_revoked': revoked,
    })
    return JsonResponse({'ok': True, 'sessions_revoked': revoked})


@require_POST
@api_player_manager_required
def api_edit_bettor(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    try:
        acc = _scoped_bettors(request.user).get(pk=data.get('id'))
    except (BettorAccount.DoesNotExist, TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Account not found'})
    if not request.user.is_superuser and acc.is_group_owner_player:
        return JsonResponse({'ok': False, 'error': 'You cannot change your own owner player login'})
    before = {'phone': acc.phone, 'balance': acc.balance, 'hot_limits': dict(acc.hot_limits or {}),
              'multiplier': acc.multiplier, 'is_active': acc.is_active}
    was_active = acc.is_active
    # Reassignment is a superuser-only action, otherwise a shop owner could move
    # a player out of their group and orphan it. Reject the attempt rather than
    # dropping the field, so the owner is never told "saved" about a change that
    # did not happen.
    if 'group_id' in data:
        if not request.user.is_superuser:
            return JsonResponse({'ok': False, 'error': 'Only an administrator can move a player to another group'})
        group_id = data.get('group_id')
        if group_id in (None, '', 0):
            acc.group = None
        else:
            try:
                group = PlayerGroup.objects.get(pk=int(group_id))
            except (PlayerGroup.DoesNotExist, TypeError, ValueError):
                return JsonResponse({'ok': False, 'error': 'Group not found'})
            if group.is_full and acc.group_id != group.pk:
                return JsonResponse({'ok': False, 'error': f'"{group.name}" already has the maximum of {MAX_GROUP_PLAYERS} players'})
            acc.group = group
    if 'phone' in data:
        acc.phone = (data['phone'] or '').strip()
    if 'balance' in data and str(data.get('balance') or '').strip() != '':
        balance = _clean_balance(data.get('balance'))
        if balance is None:
            return JsonResponse({'ok': False, 'error': 'Balance must be a whole number between 0 and 2147483647'})
        acc.balance = balance
    if 'hot_limits' in data:
        cleaned_limits = _clean_hot_limits(data.get('hot_limits'))
        if cleaned_limits is None:
            return JsonResponse({'ok': False, 'error': 'Hot limits must be a 00-99:amount object'})
        acc.hot_limits = cleaned_limits
    if 'multiplier' in data:
        acc.multiplier = _multiplier_value(data['multiplier'], acc.multiplier)
    if 'is_active' in data:
        try:
            acc.is_active = _bool_value(data['is_active'], acc.is_active)
        except ValueError as exc:
            return _flag_error(exc)
    password = (data.get('password') or '').strip()
    if password:
        password_error = _validate_new_password(password)
        if password_error:
            return JsonResponse({'ok': False, 'error': password_error})
        acc.set_password(password)
    acc.save()
    if was_active and not acc.is_active:
        action = 'suspend'
    elif not was_active and acc.is_active:
        action = 'activate'
    elif password:
        action = 'reset_password'
    else:
        action = 'update'
    revoked = _revoke_sessions(bettor_account_id=acc.pk) if password or action in ('suspend', 'activate') else 0
    log_audit(request, action, 'player', acc, {
        'changed': {k: [before[k], getattr(acc, k)] for k in before if before[k] != getattr(acc, k)},
        'password_changed': bool(password), 'sessions_revoked': revoked,
        'group': acc.group.name if acc.group_id else '',
    })
    return JsonResponse({'ok': True, 'account': acc.to_dict(), 'sessions_revoked': revoked})


# ===== Player groups (one shop owner + that owner's players) =====

def _unique_group_player_username(owner):
    """A player-login name for the owner's own dual-role entry.

    The owner's own login is created automatically when the group is made, so it
    has to dodge any existing player name rather than fail the whole request.
    """
    base = (owner.get_username() or 'owner')[:44] or 'owner'
    candidate, suffix = base, 2
    while BettorAccount.objects.filter(username=candidate).exists():
        candidate = f'{base}-{suffix}'
        suffix += 1
    return candidate


@api_player_manager_required
@require_GET
def api_list_groups(request):
    """Groups the caller may see: every group for a superuser, own group otherwise."""
    if request.user.is_superuser:
        groups = PlayerGroup.objects.select_related('owner', 'owner_player').all()
    else:
        groups = PlayerGroup.objects.select_related('owner', 'owner_player').filter(owner=request.user)
    return JsonResponse({'ok': True, 'groups': [g.to_dict() for g in groups], 'max_players': MAX_GROUP_PLAYERS})


@require_POST
@api_superuser_required
def api_create_group(request):
    """Create a group and give its owner their own player login.

    The owner row is what makes "Owner" mean shop owner and player at once, so
    it is created here rather than left as a second manual step.
    """
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    name = (data.get('name') or '').strip()
    if not name or len(name) > 100:
        return JsonResponse({'ok': False, 'error': 'Group name is required (max 100 characters)'})
    owner_id = data.get('owner_id')
    if owner_id in (None, ''):
        return JsonResponse({'ok': False, 'error': 'Choose an owner for this group'})
    try:
        owner = User.objects.get(pk=owner_id, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Owner not found or suspended'})
    if PlayerGroup.objects.filter(name=name).exists():
        return JsonResponse({'ok': False, 'error': f'"{name}" already exists'})
    if PlayerGroup.objects.filter(owner=owner).exists():
        return JsonResponse({'ok': False, 'error': f'"{owner.username}" already owns a group'})

    # The owner's own player login. It carries an unusable password hash: this
    # account is reached through the owner's Django sign-in, not a player
    # password, so a leaked hash cannot be used to sign in as the player.
    owner_player = BettorAccount(
        username=_unique_group_player_username(owner),
        group=None,
        hot_limits={},
        balance=_clean_balance(data.get('owner_balance', 0)) or 0,
    )
    owner_player.set_password(secrets.token_urlsafe(32))
    owner_player.save()

    group = PlayerGroup.objects.create(name=name, owner=owner, owner_player=owner_player)
    owner_player.group = group
    owner_player.save()
    log_audit(request, 'create', 'group', group, {
        'name': group.name, 'owner': owner.username, 'owner_player': owner_player.username,
    })
    return JsonResponse({'ok': True, 'group': group.to_dict()})


@require_POST
@api_superuser_required
def api_edit_group(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    try:
        group = PlayerGroup.objects.get(pk=data.get('id'))
    except (PlayerGroup.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Group not found'})
    name = (data.get('name') or '').strip()
    if not name or len(name) > 100:
        return JsonResponse({'ok': False, 'error': 'Group name is required (max 100 characters)'})
    clash = PlayerGroup.objects.filter(name=name).exclude(pk=group.pk)
    if clash.exists():
        return JsonResponse({'ok': False, 'error': f'"{name}" already exists'})
    before = group.name
    group.name = name
    group.save()
    log_audit(request, 'update', 'group', group, {'changed': {'name': [before, name]}})
    return JsonResponse({'ok': True, 'group': group.to_dict()})


@require_POST
@api_superuser_required
def api_delete_group(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    try:
        group = PlayerGroup.objects.get(pk=data.get('id'))
    except (PlayerGroup.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Group not found'})
    members = group.players.all()
    member_names = [p.username for p in members]
    revoked = 0
    for player in members:
        revoked += _revoke_sessions(bettor_account_id=player.pk)
    name, owner_username = group.name, group.owner.username
    # owner_player is SET_NULL on the group and SET_NULL on the player side, so
    # deleting the group leaves the rows rather than cascading a balance away.
    group.delete()
    log_audit(request, 'delete', 'group', None, {
        'name': name, 'owner': owner_username,
        'released_players': member_names, 'sessions_revoked': revoked,
    })
    return JsonResponse({'ok': True, 'released_players': member_names, 'sessions_revoked': revoked})


def bettor_login_page(request):
    response = render(request, 'twodapp/bettor_login.html')
    response['Content-Security-Policy'] = "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'"
    return response


@user_passes_test(lambda u: u.is_authenticated and u.is_active and u.is_superuser)
def manage_bettors_page(request):
    return redirect(f"{reverse('react_admin')}?tab=players")


# ===== Operator Panel (Owner accounts + Player accounts) =====
# Owner-account management is restricted to superusers only.

def _operator_serialize(u):
    return {
        'id': u.pk,
        'username': u.username,
        'email': u.email,
        'first_name': u.first_name,
        'last_name': u.last_name,
        'is_superuser': u.is_superuser,
        'is_staff': u.is_staff,
        'is_active': u.is_active,
        'last_login': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '',
        'date_joined': u.date_joined.strftime('%Y-%m-%d') if u.date_joined else '',
    }


@user_passes_test(lambda u: u.is_authenticated and u.is_active and u.is_superuser)
def operator_panel_page(request):
    return redirect(reverse('react_admin'))


@api_superuser_required
@require_GET
def api_list_operators(request):
    users = [_operator_serialize(u) for u in User.objects.all().order_by('-is_superuser', '-is_staff', 'username')]
    return JsonResponse({'ok': True, 'operators': users})


@require_POST
@api_superuser_required
def api_create_operator(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    email = (data.get('email') or '').strip()
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    try:
        is_staff = _bool_value(data.get('is_staff'))
        is_superuser = _bool_value(data.get('is_superuser'))
        is_active = _bool_value(data.get('is_active'), True)
    except ValueError as exc:
        return _flag_error(exc)
    if not username or not password:
        return JsonResponse({'ok': False, 'error': 'Username + password required'})
    password_error = _validate_new_password(password)
    if password_error:
        return JsonResponse({'ok': False, 'error': password_error})
    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({'ok': False, 'error': f'"{username}" already exists'})
    if User.objects.filter(email__iexact=email).exists() and email:
        return JsonResponse({'ok': False, 'error': f'Email "{email}" already used'})
    user = User.objects.create_user(
        username=username, password=password, email=email,
        first_name=first_name, last_name=last_name,
        is_staff=is_staff, is_superuser=is_superuser, is_active=is_active,
    )
    log_audit(request, 'create', 'owner', user, {
        'is_staff': is_staff, 'is_superuser': is_superuser, 'is_active': is_active,
    })
    return JsonResponse({'ok': True, 'operator': _operator_serialize(user)})


@require_POST
@api_superuser_required
def api_edit_operator(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    uid = data.get('id')
    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Owner account not found'})
    if user.pk == request.user.pk:
        # Refuse rather than silently ignore, so the caller is not told the
        # change succeeded when it did not happen.
        requested = {}
        if 'is_superuser' in data and _flag_bool(data['is_superuser'], user.is_superuser) != user.is_superuser:
            requested['is_superuser'] = data['is_superuser']
        if 'is_staff' in data and _flag_bool(data['is_staff'], user.is_staff) != user.is_staff:
            requested['is_staff'] = data['is_staff']
        if 'is_active' in data and _flag_bool(data['is_active'], user.is_active) != user.is_active:
            requested['is_active'] = data['is_active']
        if requested:
            names = ', '.join(sorted(requested))
            return JsonResponse({
                'ok': False,
                'error': f'You cannot change your own {names}. Ask another superuser to do it.',
            })
        is_superuser = user.is_superuser
        is_staff = user.is_staff
        is_active = user.is_active
    else:
        try:
            is_superuser = _bool_value(data.get('is_superuser'), user.is_superuser)
            is_staff = _bool_value(data.get('is_staff'), user.is_staff)
            is_active = _bool_value(data.get('is_active'), user.is_active)
        except ValueError as exc:
            return _flag_error(exc)
    before = {'email': user.email, 'first_name': user.first_name, 'last_name': user.last_name,
              'is_superuser': user.is_superuser, 'is_staff': user.is_staff, 'is_active': user.is_active}
    was_active, was_superuser = user.is_active, user.is_superuser
    user.email = (data.get('email') if 'email' in data else user.email) or ''
    if 'first_name' in data:
        user.first_name = (data.get('first_name') or '').strip()
    if 'last_name' in data:
        user.last_name = (data.get('last_name') or '').strip()
    if user.pk != request.user.pk:
        lockout_error = _last_superuser_guard(user, is_superuser, is_active)
        if lockout_error:
            return JsonResponse({'ok': False, 'error': lockout_error})
        user.is_superuser = is_superuser
        user.is_staff = is_staff
        user.is_active = is_active
    password = (data.get('password') or '').strip()
    if password:
        password_error = _validate_new_password(password, user)
        if password_error:
            return JsonResponse({'ok': False, 'error': password_error})
        user.set_password(password)
    user.save()
    if was_active and not user.is_active:
        action = 'suspend'
    elif not was_active and user.is_active:
        action = 'activate'
    elif password:
        action = 'reset_password'
    else:
        action = 'update'
    revoked = _revoke_sessions(user_id=user.pk) if password or action in ('suspend', 'activate') else 0
    log_audit(request, action, 'owner', user, {
        'changed': {k: [before[k], getattr(user, k)] for k in before if before[k] != getattr(user, k)},
        'was_superuser': was_superuser, 'password_changed': bool(password), 'sessions_revoked': revoked,
    })
    return JsonResponse({'ok': True, 'operator': _operator_serialize(user), 'sessions_revoked': revoked})


@require_POST
@api_superuser_required
def api_reset_operator_password(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    uid = data.get('id')
    password = (data.get('password') or '').strip()
    if not password:
        return JsonResponse({'ok': False, 'error': 'Password required'})
    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Owner account not found'})
    password_error = _validate_new_password(password, user)
    if password_error:
        return JsonResponse({'ok': False, 'error': password_error})
    user.set_password(password)
    user.save()
    revoked = _revoke_sessions(user_id=user.pk)
    log_audit(request, 'reset_password', 'owner', user, {'sessions_revoked': revoked})
    return JsonResponse({'ok': True, 'sessions_revoked': revoked})


@require_POST
@api_superuser_required
def api_delete_operator(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON body'})
    uid = data.get('id')
    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Owner account not found'})
    if user.pk == request.user.pk:
        return JsonResponse({'ok': False, 'error': 'မိမိကိုယ်တိုင်ရဲ့ အကောင့်ကို ဖျက်လို့ မရပါ'})
    lockout_error = _last_superuser_guard(user, False, False)
    if lockout_error:
        return JsonResponse({'ok': False, 'error': lockout_error})
    # A player group points at its owner with PROTECT, so deleting an owner who
    # still owns one would raise an unhandled ProtectedError. Say so plainly
    # instead of returning a 500.
    group = PlayerGroup.objects.filter(owner=user).first()
    if group is not None:
        return JsonResponse({'ok': False, 'error': f'"{user.username}" still owns the player group "{group.name}". Delete the group first.'})
    username, was_superuser = user.username, user.is_superuser
    revoked = _revoke_sessions(user_id=user.pk)
    user.delete()
    log_audit(request, 'delete', 'owner', None, {
        'username': username, 'was_superuser': was_superuser, 'sessions_revoked': revoked,
    })
    return JsonResponse({'ok': True, 'sessions_revoked': revoked})


@require_POST
def api_bettor_login(request):
    data = json.loads(request.body)
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    try:
        acc = BettorAccount.objects.get(username=username, is_active=True)
    except BettorAccount.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Account not found'})
    if not acc.check_password(password):
        return JsonResponse({'ok': False, 'error': 'Wrong password'})
    from django.utils import timezone
    acc.last_user_agent = request.META.get('HTTP_USER_AGENT', '')[:300]
    acc.last_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))[:50]
    acc.last_seen = timezone.now()
    acc.save()
    request.session['bettor_account_id'] = acc.pk
    request.session['bettor_username'] = acc.username
    return JsonResponse({'ok': True, 'redirect': '/bet/?type=bettor'})


@api_login_required
@require_GET
def api_bettor_profile(request):
    acc = _resolve_bettor(request)
    if not acc:
        return JsonResponse({'ok': False, 'error': 'Not logged in as bettor'})
    return JsonResponse({'ok': True, 'account': acc.to_dict()})


@api_login_required
def chat_page(request):
    return render(request, 'twodapp/chat.html', {'chat_role': 'owner'})


@api_login_required
def settings_page(request):
    is_owner = request.user.is_authenticated
    state = GameState.get_state()
    logs = [_serialize_log(l) for l in OperationLog.objects.order_by('-id')[:200]]
    return render(request, 'twodapp/settings.html', {
        'is_owner': is_owner,
        'global_limit': state.global_limit or '',
        'specific_limits_json': json.dumps(dict(state.specific_limits)),
        'logs_json': json.dumps(logs),
    })


@api_login_required
def bettor_settings_page(request):
    acc = _resolve_bettor(request)
    # Owner-set per-player hot limits, ordered for display. Read-only: the
    # player sees what the owner configured and cannot change it here.
    hot_limits = []
    for number, amount in (acc.hot_limits or {}).items() if acc else []:
        hot_limits.append({
            'num': str(number),
            'amount': amount,
            'amount_display': f'{amount:,}' if isinstance(amount, (int, float)) else str(amount),
        })
    hot_limits.sort(key=lambda item: (len(item['num']), item['num']))
    return render(request, 'twodapp/settings.html', {
        'is_owner': False,
        'is_bettor': True,
        'bettor_account': acc.to_dict() if acc else None,
        'bettor_username': request.session.get('bettor_username') or (acc.username if acc else ''),
        'bettor_hot_limits': hot_limits,
        'global_limit': '',
        'specific_limits_json': json.dumps({}),
        'logs_json': json.dumps([]),
    })


@require_POST
@api_login_required
def api_change_password(request):
    data = json.loads(request.body)
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    if not old_password or not new_password:
        return JsonResponse({'ok': False, 'error': 'Passwords required'})
    if len(new_password) < 4:
        return JsonResponse({'ok': False, 'error': 'Password must be at least 4 characters'})
    user = request.user
    if not user.check_password(old_password):
        return JsonResponse({'ok': False, 'error': 'Wrong current password'})
    user.set_password(new_password)
    user.save()
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_bettor_change_password(request):
    data = json.loads(request.body)
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    if not old_password or not new_password:
        return JsonResponse({'ok': False, 'error': 'Passwords required'})
    if len(new_password) < 4:
        return JsonResponse({'ok': False, 'error': 'New password must be at least 4 characters'})
    acc = _resolve_bettor(request)
    if not acc:
        return JsonResponse({'ok': False, 'error': 'Not logged in as player'})
    if not acc.check_password(old_password):
        return JsonResponse({'ok': False, 'error': 'Wrong current password'})
    acc.set_password(new_password)
    acc.save()
    return JsonResponse({'ok': True})


@api_login_required
def bettor_chat_page(request):
    return render(request, 'twodapp/chat.html', {'chat_role': 'player'})


def chat_identity(request):
    if request.user.is_authenticated:
        return 'owner', request.user.username
    return 'player', request.session.get('bettor_username', 'Player')


@require_POST
@api_login_required
def api_chat_send(request):
    data = json.loads(request.body)
    message = (data.get('message') or '').strip()
    if not message:
        return JsonResponse({'ok': False, 'error': 'Empty message'})
    sender_type, sender_name = chat_identity(request)
    reply_to = None
    if data.get('reply_to'):
        try:
            reply_to = ChatMessage.objects.get(pk=int(data['reply_to']))
        except (ChatMessage.DoesNotExist, ValueError, TypeError):
            reply_to = None
    msg = ChatMessage.objects.create(
        sender_type=sender_type, sender_name=sender_name,
        message=message, reply_to=reply_to,
    )
    return JsonResponse({'ok': True, 'msg_id': msg.id})


@require_GET
@api_login_required
def api_chat_poll(request):
    after_id_str = request.GET.get('after', '0') or '0'
    try:
        after_id = int(after_id_str)
    except (ValueError, TypeError):
        after_id = 0
    last_sync = request.GET.get('sync', '')
    me_type, me_name = chat_identity(request)
    # Update my presence (last seen)
    presence, _ = ChatPresence.objects.get_or_create(user_type=me_type, user_name=me_name)
    presence.last_seen = timezone.now()

    # Mark messages from the other party as read when I poll and bump updated_at
    # so the sender's read-receipt ticks refresh.
    unread = list(ChatMessage.objects.exclude(sender_type=me_type).filter(is_read=False))
    if unread:
        ChatMessage.objects.filter(pk__in=[m.pk for m in unread]).update(
            is_read=True, updated_at=timezone.now())

    # Delta query: new messages (id > after_id) OR messages modified since last_sync.
    q_conditions = Q(id__gt=after_id)
    if last_sync:
        try:
            ts = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt_timezone.utc)
            q_conditions |= Q(updated_at__gt=ts)
        except (ValueError, TypeError):
            pass
    msgs = list(ChatMessage.objects.filter(q_conditions).order_by('id')[:300])

    data = []
    by_id = {}
    for m in msgs:
        by_id[m.id] = m
    for m in msgs:
        reactions = {}
        for r in m.reactions.all():
            reactions.setdefault(r.emoji, {'count': 0, 'users': []})
            reactions[r.emoji]['count'] += 1
            reactions[r.emoji]['users'].append(f"{r.user_type}:{r.user_name}")
        reply = by_id.get(m.reply_to_id) if m.reply_to_id else None
        data.append({
            'id': m.id,
            'sender_type': m.sender_type,
            'sender_name': m.sender_name,
            'message': '' if m.is_deleted else m.message,
            'photo': (m.photo.url if m.photo else None) and (None if m.is_deleted else m.photo.url),
            'audio': m.audio.url if (m.audio and not m.is_deleted) else None,
            'is_deleted': m.is_deleted,
            'is_pinned': m.is_pinned,
            'edited': bool(m.edited_at),
            'read': m.is_read,
            'time': m.created_at.astimezone(MMT).strftime('%H:%M'),
            'date': m.created_at.astimezone(MMT).strftime('%Y-%m-%d'),
            'reply_to': {
                'id': reply.id,
                'sender_type': reply.sender_type,
                'sender_name': reply.sender_name,
                'message': reply.message if not reply.is_deleted else '',
                'is_deleted': reply.is_deleted,
                'photo': reply.photo.url if (reply.photo and not reply.is_deleted) else None,
                'audio': reply.audio.url if (reply.audio and not reply.is_deleted) else None,
            } if reply else None,
            'reactions': reactions,
        })
    presence.save(update_fields=['last_seen'])

    # Presence of the other party
    other_type = 'player' if me_type == 'owner' else 'owner'
    other_presence = ChatPresence.objects.filter(user_type=other_type).first()
    now = timezone.now()
    if other_presence:
        delta = (now - other_presence.last_seen).total_seconds()
        other_online = delta < 90
        other_typing = other_presence.is_typing and other_online
    else:
        other_presence = None
        other_online = False
        other_typing = False

    return JsonResponse({'ok': True, 'messages': data, 'server_time': now.isoformat(), 'presence': {
        'online': other_online,
        'typing': other_typing,
        'last_seen': other_presence.last_seen.astimezone(MMT).strftime('%H:%M') if other_presence else None,
    }})


@require_POST
@api_login_required
def api_chat_clear(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    ChatMessage.objects.all().delete()
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_edit(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    data = json.loads(request.body)
    msg_id = data.get('id')
    message = (data.get('message') or '').strip()
    me_type, me_name = chat_identity(request)
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    if msg.sender_type != me_type:
        return JsonResponse({'ok': False, 'error': 'Cannot edit others'})
    if not message:
        return JsonResponse({'ok': False, 'error': 'Empty message'})
    msg.message = message
    msg.edited_at = timezone.now()
    msg.updated_at = timezone.now()
    msg.save(update_fields=['message', 'edited_at', 'updated_at'])
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_delete(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    data = json.loads(request.body)
    msg_id = data.get('id')
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    msg.is_deleted = True
    msg.message = ''
    msg.updated_at = timezone.now()
    msg.save(update_fields=['is_deleted', 'message', 'updated_at'])
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_typing(request):
    data = json.loads(request.body)
    is_typing = bool(data.get('typing'))
    me_type, me_name = chat_identity(request)
    presence, _ = ChatPresence.objects.get_or_create(user_type=me_type, user_name=me_name)
    presence.is_typing = is_typing
    presence.last_seen = timezone.now()
    presence.save(update_fields=['is_typing', 'last_seen'])
    return JsonResponse({'ok': True})


@require_POST
@api_login_required
def api_chat_pin(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'Owner only'})
    data = json.loads(request.body)
    msg_id = data.get('id')
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    msg.is_pinned = not msg.is_pinned
    msg.updated_at = timezone.now()
    msg.save(update_fields=['is_pinned', 'updated_at'])
    return JsonResponse({'ok': True, 'is_pinned': msg.is_pinned})


EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🔥', '💯', '🙏']


@require_POST
@api_login_required
def api_chat_react(request):
    data = json.loads(request.body)
    msg_id = data.get('id')
    emoji = data.get('emoji', '')
    if emoji not in EMOJIS:
        return JsonResponse({'ok': False, 'error': 'Invalid emoji'})
    try:
        msg = ChatMessage.objects.get(pk=msg_id)
    except ChatMessage.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Not found'})
    if request.user.is_authenticated:
        user_type, user_name = 'owner', request.user.username
    else:
        user_type = 'player'
        user_name = request.session.get('bettor_username', 'Player')
    existing = ChatReaction.objects.filter(message=msg, emoji=emoji, user_type=user_type, user_name=user_name)
    if existing.exists():
        existing.delete()
        toggled = False
    else:
        ChatReaction.objects.create(message=msg, emoji=emoji, user_type=user_type, user_name=user_name)
        toggled = True
    reactions = {}
    for r in msg.reactions.all():
        reactions.setdefault(r.emoji, {'count': 0, 'users': []})
        reactions[r.emoji]['count'] += 1
        reactions[r.emoji]['users'].append(f"{r.user_type}:{r.user_name}")
    msg.updated_at = timezone.now()
    msg.save(update_fields=['updated_at'])
    return JsonResponse({'ok': True, 'toggled': toggled, 'reactions': reactions})


@require_POST
@api_login_required
def api_chat_upload_photo(request):
    photo = request.FILES.get('photo')
    if not photo:
        return JsonResponse({'ok': False, 'error': 'No photo'})
    if photo.size > 5 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': 'Max 5MB'})
    if not photo.content_type.startswith('image/'):
        return JsonResponse({'ok': False, 'error': 'Images only'})
    caption = request.POST.get('caption', '').strip()
    if request.user.is_authenticated:
        sender_type, sender_name = 'owner', request.user.username
    else:
        sender_type = 'player'
        sender_name = request.session.get('bettor_username', 'Player')
    msg = ChatMessage.objects.create(
        sender_type=sender_type, sender_name=sender_name,
        message=caption, photo=photo
    )
    photo_url = msg.photo.url
    return JsonResponse({'ok': True, 'photo_url': photo_url, 'msg_id': msg.id})


@require_POST
@api_login_required
def api_chat_upload_audio(request):
    audio = request.FILES.get('audio')
    if not audio:
        return JsonResponse({'ok': False, 'error': 'No audio'})
    if audio.size > 10 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': 'Max 10MB'})
    if not audio.content_type.startswith('audio/'):
        return JsonResponse({'ok': False, 'error': 'Audio only'})
    sender_type, sender_name = chat_identity(request)
    msg = ChatMessage.objects.create(
        sender_type=sender_type, sender_name=sender_name,
        message='', audio=audio
    )
    return JsonResponse({'ok': True, 'audio_url': msg.audio.url, 'msg_id': msg.id})
