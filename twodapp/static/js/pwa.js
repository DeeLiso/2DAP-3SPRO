(function () {
    if (!('serviceWorker' in navigator)) return;
    if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') return;

    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function (err) {
            console.error('SW registration failed:', err);
        });
    });
})();

(function () {
    var KEY_DISMISSED = 'pwa-banner-dismissed';
    var KEY_INSTALLED = 'pwa-installed';

    var store = {
        get: function (k) {
            try { return localStorage.getItem(k); } catch (e) { return null; }
        },
        set: function (k, v) {
            try { localStorage.setItem(k, v); } catch (e) { }
        }
    };

    var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    var isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;

    if (isStandalone || store.get(KEY_INSTALLED) === '1') return;
    if (store.get(KEY_DISMISSED) === '1') return;

    var deferredPrompt = null;
    var banner = null;
    var installBtn = null;
    var hintEl = null;

    var build = function () {
        banner = document.createElement('div');
        banner.className = 'pwa-banner';
        banner.setAttribute('role', 'dialog');
        banner.setAttribute('aria-label', 'App ထည့်သုံးရန်');

        var text = document.createElement('div');
        text.className = 'pwa-banner-text';

        var title = document.createElement('strong');
        title.textContent = '2DAP-3SPRO';

        hintEl = document.createElement('span');
        text.appendChild(title);
        text.appendChild(hintEl);

        installBtn = document.createElement('button');
        installBtn.type = 'button';
        installBtn.className = 'pwa-banner-btn';
        installBtn.textContent = 'Install';

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'pwa-banner-x';
        close.setAttribute('aria-label', 'ပိတ်ရန်');
        close.textContent = '×';

        banner.appendChild(text);
        banner.appendChild(installBtn);
        banner.appendChild(close);
        document.body.appendChild(banner);

        installBtn.addEventListener('click', onInstall);
        close.addEventListener('click', function () {
            store.set(KEY_DISMISSED, '1');
            hide();
        });

        requestAnimationFrame(function () {
            banner.classList.add('pwa-banner-show');
        });
    };

    var hide = function () {
        if (!banner) return;
        banner.classList.remove('pwa-banner-show');
        window.setTimeout(function () {
            if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
            banner = null;
        }, 300);
    };

    var setMode = function (mode) {
        if (!banner) return;
        banner.dataset.mode = mode;
        if (mode === 'ios') {
            hintEl.textContent = 'Share နဲ့ Add to Home Screen နဲ့ ဖုန်းထဲမှာ ထည့်ပါ';
            installBtn.hidden = true;
        } else {
            hintEl.textContent = 'ဖုန်းထဲမှာ app အဖြစ် ထည့်သုံးပါ';
            installBtn.hidden = false;
        }
    };

    function onInstall() {
        if (!deferredPrompt) return;
        installBtn.disabled = true;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function (choice) {
            if (choice && choice.outcome === 'accepted') store.set(KEY_INSTALLED, '1');
            store.set(KEY_DISMISSED, '1');
            deferredPrompt = null;
            hide();
        });
    }

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;
        if (!banner) {
            build();
            setMode('native');
        }
    });

    window.addEventListener('appinstalled', function () {
        store.set(KEY_INSTALLED, '1');
        store.set(KEY_DISMISSED, '1');
        hide();
    });

    if (isIos && !deferredPrompt) {
        window.setTimeout(function () {
            if (banner || store.get(KEY_DISMISSED) === '1') return;
            build();
            setMode('ios');
        }, 2500);
    }
})();
