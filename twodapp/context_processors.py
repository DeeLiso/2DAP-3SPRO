from pathlib import Path

from django.conf import settings

# The bundles under this directory are rebuilt far more often than the server is
# restarted, so the cache-busting query string is derived from their mtimes
# instead of a hand-maintained number. A hardcoded version leaves browsers
# holding the previous CSS/JS after a rebuild, which looks exactly like a change
# that "does not work" in the browser.
_APP_BUNDLE_DIR = Path(settings.BASE_DIR) / 'twodapp' / 'static' / 'app'
_APP_BUNDLES = ('app.css', 'app.js')


def _app_bundle_version() -> str:
    newest = 0.0
    for name in _APP_BUNDLES:
        try:
            newest = max(newest, (_APP_BUNDLE_DIR / name).stat().st_mtime)
        except OSError:
            # A missing bundle means the frontend has not been built yet; fall
            # through to the fallback so the page still renders.
            continue
    return str(int(newest)) if newest else ''


def app_version(request):
    return {
        'app_version': getattr(settings, 'APP_VERSION', '1.0.0'),
        'static_asset_version': _app_bundle_version() or getattr(settings, 'STATIC_ASSET_VERSION', '1'),
    }
