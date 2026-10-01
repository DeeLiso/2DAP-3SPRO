import os
import re
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django_ok = True
try:
    import django
    django.setup()
except Exception as exc:  # noqa: BLE001
    django_ok = False
    print('django setup failed:', exc)

root = os.path.dirname(os.path.abspath(__file__))
src_css = open(os.path.join(root, 'frontend', 'src', 'styles.css'), encoding='utf-8').read()
built_css = open(os.path.join(root, 'twodapp', 'static', 'app', 'app.css'), encoding='utf-8').read()
built_js = open(os.path.join(root, 'twodapp', 'static', 'app', 'app.js'), encoding='utf-8').read()
component = open(os.path.join(root, 'frontend', 'src', 'components', 'AdminScreen.tsx'), encoding='utf-8').read()
settings_py = open(os.path.join(root, 'config', 'settings.py'), encoding='utf-8').read()
ctx = open(os.path.join(root, 'twodapp', 'context_processors.py'), encoding='utf-8').read()
react_html = open(os.path.join(root, 'twodapp', 'templates', 'twodapp', 'react_app.html'), encoding='utf-8').read()
sw = open(os.path.join(root, 'twodapp', 'static', 'sw.js'), encoding='utf-8').read()

fails = []


def check(label, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + label + (('  -> ' + detail) if detail else ''))
    if not ok:
        fails.append(label)


print('--- 1. theme variable blocks per theme ---')
themes = {
    'teal': ('#0f766e', '#0b5b55', '#0b5b55', '#073f3a'),
    'indigo': ('#4338ca', '#3730a3', '#3730a3', '#2a2480'),
    'ocean': ('#0369a1', '#075985', '#075985', '#043f57'),
    'violet': ('#6d28d9', '#5b21b6', '#5b21b6', '#451a8c'),
    'amber': ('#b45309', '#92400e', '#92400e', '#6b2c07'),
    'crimson': ('#be123c', '#9f1239', '#9f1239', '#7a0c2c'),
}
for name, (accent, deep, chrome, chrome_deep) in themes.items():
    m = re.search(r"\.admin-page\[data-accent='" + name + r"'\] \{(.*?)\}", src_css, re.S)
    block = m.group(1) if m else ''
    ok = bool(m) and all(t in block for t in (accent, deep, chrome, chrome_deep, '--accent-rgb', '--accent-soft'))
    check(f'theme block {name}', ok, 'vars: accent/deep/chrome/chrome-deep/soft/rgb')

print('--- 2. header + sidebar surfaces are theme driven ---')
check('admin-header uses --chrome', bool(re.search(r'\.admin-header \{[^}]*background: var\(--chrome, var\(--ink\)\)', src_css, re.S)))
check('admin-sidebar uses --chrome-deep', bool(re.search(r'\.admin-sidebar \{[^}]*background: var\(--chrome-deep, var\(--surface\)\)', src_css, re.S)))
check('admin-page canvas tinted per theme', bool(re.search(r'\.admin-page\[data-accent\] \{\s*background: var\(--accent-soft-2\)', src_css)))
check('mobile drawer uses --chrome-deep', bool(re.search(r'\.admin-sidebar \{[^}]*background: var\(--chrome-deep, var\(--surface\)\);[^}]*border-right: 1px solid rgba\(255, 255, 255, 0.12\)', src_css)))
check('no hardcoded --ink header bg left', 'background: var(--ink);' not in src_css)

print('--- 3. sidebar text contrast tokens ---')
tokens = {
    'sidebar text light': '--sidebar-text: rgba(240, 250, 245, 0.94)',
    'sidebar muted light': '--sidebar-muted: rgba(228, 244, 236, 0.6)',
    'sidebar line light': '--sidebar-line: rgba(255, 255, 255, 0.14)',
    'sidebar hover light': '--sidebar-hover: rgba(255, 255, 255, 0.1)',
}
for label, token in tokens.items():
    check(f'defined: {label}', token in src_css)
uses = {
    'nav item text': r'\.sidebar-nav-item \{[^}]*color: var\(--sidebar-text',
    'nav item hover': r'\.sidebar-nav-item:hover \{[^}]*color: #ffffff;[^}]*background: var\(--sidebar-hover',
    'sidebar label': r'\.sidebar-label,\s*\.sidebar-rail-number \{[^}]*color: var\(--sidebar-muted',
    'operator name': r'\.sidebar-operator strong \{[^}]*color: var\(--sidebar-text',
    'operator role': r'\.sidebar-operator small \{[^}]*color: var\(--sidebar-muted',
    'security line': r'\.sidebar-security \{[^}]*color: var\(--sidebar-muted',
    'theme label': r'\.sidebar-accent-label \{[^}]*color: var\(--sidebar-muted',
    'bottom border': r'\.sidebar-bottom \{[^}]*border-top: 1px solid var\(--sidebar-line',
}
for label, pat in uses.items():
    check(f'applied: {label}', bool(re.search(pat, src_css, re.S)))
bare_dark = []
for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', src_css):
    sel, body = m.group(1).strip(), m.group(2)
    if 'sidebar' not in sel:
        continue
    for decl in body.split(';'):
        decl = decl.strip()
        if not decl:
            continue
        if re.search(r':\s*#(5f7068|10221b)\s*$', decl) or re.search(r':\s*var\(--(?:ink|muted)\)\s*$', decl):
            bare_dark.append((src_css[:m.start()].count('\n') + 1, sel, decl))
check('no bare dark color declarations in sidebar rules', not bare_dark, str(bare_dark[:4]))
check('rail number light', bool(re.search(r'\.sidebar-rail-number \{[^}]*color: rgba\(255, 255, 255, 0.86\)', src_css, re.S)))
check('avatar dark text on light tint', bool(re.search(r'\.sidebar-operator-avatar \{[^}]*color: var\(--teal-deep\);[^}]*background: var\(--accent-soft\)', src_css, re.S)))
check('nav count light', bool(re.search(r'\.sidebar-nav-count \{[^}]*color: rgba\(240, 250, 245, 0\.78\);[^}]*background: rgba\(255, 255, 255, 0\.16\)', src_css, re.S)))
check('active nav keeps light pill on dark sidebar', bool(re.search(r'\.sidebar-nav-item\.is-active \{[^}]*color: var\(--teal-deep\);[^}]*background: var\(--accent-soft\)', src_css, re.S)))
check('swatch active ring is white based', 'box-shadow: 0 0 0 2px var(--chrome-deep, var(--surface)), 0 0 0 4px rgba(255, 255, 255, 0.85)' in src_css)
check('access-card has accent border', bool(re.search(r'\.access-card \{[^}]*border: 1px solid rgba\(var\(--accent-rgb\), 0\.16\)', src_css, re.S)))

print('--- 4. react component ---')
check('data-accent on admin-page', 'data-accent={accent}' in component)
check('localStorage read', "ACCENT_STORAGE_KEY = 'twodap-admin-accent'" in component)
check('localStorage write', 'window.localStorage.setItem(ACCENT_STORAGE_KEY, accent)' in component)
check('validated fallback to teal', "return 'teal'" in component)
check('switcher present', 'sidebar-accent-options' in component)
check('radiogroup a11y', 'role="radiogroup"' in component and 'aria-checked={accent === option.id}' in component)
check('6 swatches', component.count('{accentOptions.map((option)') == 1)
check('inline style NOT used for swatch color (CSP safe)', 'style={{ background: option.swatch }}' not in component)
check('Check icon imported', re.search(r'\bCheck,\n', component) is not None)

print('--- 5. cache busting versions aligned ---')
sv = re.search(r"STATIC_ASSET_VERSION', '(\d+)'", settings_py)
wv = re.search(r"const VERSION = 'v(\d+)'", sw)
check('settings STATIC_ASSET_VERSION present', sv is not None, sv.group(1) if sv else '')
check('sw VERSION present', wv is not None, 'v' + wv.group(1) if wv else '')
check('settings version == sw version', sv and wv and sv.group(1) == wv.group(1), f'settings={sv.group(1) if sv else "?"} sw={wv.group(1) if wv else "?"}')
check('context processor exposes static_asset_version', "'static_asset_version'" in ctx)
check('app.css cache busted', re.search(r"app/app\.css' %\}\?v=\{\{ static_asset_version \}\}", react_html) is not None)
check('app.js cache busted', re.search(r"app/app\.js' %\}\?v=\{\{ static_asset_version \}\}", react_html) is not None)
check('pwa.js cache busted', re.search(r"js/pwa\.js' %\}\?v=\{\{ static_asset_version \}\}", react_html) is not None)
check('sw still network-first for app bundle', 'const APP_BUNDLE' in sw and 'networkFirst(request)' in sw)

print('--- 6. built output in sync with source ---')
for name, (_a, _d, _c, _cd) in themes.items():
    check(f'built css has theme {name}', f".admin-page[data-accent={name}]" in built_css)
check('built css has swatch rule', '.sidebar-accent-swatch' in built_css)
check('built css has chrome-deep', '--chrome-deep' in built_css)
check('built js has accent storage key', 'twodap-admin-accent' in built_js)
check('built js has Theme color label', 'Theme color' in built_js)
check('built js has data-accent binding', 'data-accent' in built_js)
check('swatch colors come from CSS classes', 'sidebar-accent-swatch--teal' in src_css and 'sidebar-accent-swatch--crimson' in src_css)
check('6 swatch color classes defined', len(re.findall(r'\.sidebar-accent-swatch--[a-z]+ \{ background: #[0-9a-f]{6}; \}', src_css)) == 6)
check('built js has no inline style attribute for swatches', 'style' not in built_js[built_js.find('sidebar-accent-swatch') - 400:built_js.find('sidebar-accent-swatch') + 400] if 'sidebar-accent-swatch' in built_js else False)

print('--- 7. file hygiene ---')
for rel in ['config/settings.py', 'twodapp/static/sw.js', 'twodapp/context_processors.py']:
    raw = open(os.path.join(root, rel), 'rb').read()
    check(f'{rel} pure ascii', all(b < 128 for b in raw), f'{sum(1 for b in raw if b > 127)} non-ascii')
    check(f'{rel} no mixed line endings', raw.count(b'\r\n') in (0, raw.count(b'\n')))
for junk in ['twod_theme_check.py', 'twod_make_session.py', 'twod_probe.py']:
    check(f'no stray script {junk}', not os.path.exists(os.path.join(root, junk)))

print()
print('RESULT:', 'ALL CHECKS PASSED' if not fails else f'{len(fails)} FAILED -> {fails}')
sys.exit(0 if not fails else 1)
