(function () {
    'use strict';

    var WARN_MSG = '🔒 Source code ကြည့်ရှုခြင်းကို ပိတ်ထားပါသည်';

    function showWarn() {
        var t = document.getElementById('secToast');
        if (!t) {
            t = document.createElement('div');
            t.id = 'secToast';
            t.style.cssText =
                'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);' +
                'background:rgba(15,23,42,0.94);color:#fff;' +
                'font:600 13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;' +
                'padding:10px 18px;border-radius:10px;' +
                'box-shadow:0 8px 24px rgba(0,0,0,0.35);z-index:2147483000;' +
                'opacity:0;transition:opacity .25s ease;pointer-events:none;' +
                'text-align:center;max-width:86vw';
            document.body.appendChild(t);
        }
        t.textContent = WARN_MSG;
        t.style.opacity = '1';
        clearTimeout(t._h);
        t._h = setTimeout(function () { t.style.opacity = '0'; }, 1600);
    }

    function block(e) {
        e.preventDefault();
        showWarn();
        return false;
    }

    var isEditable = function () {
        var el = document.activeElement;
        if (!el) return false;
        var tag = el.tagName;
        return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
    };

    document.addEventListener('contextmenu', block);

    document.addEventListener('keydown', function (e) {
        var k = e.keyCode || e.which;
        var ctrl = e.ctrlKey || e.metaKey;
        var shift = e.shiftKey;

        var f12 = k === 123;
        var ctrlShiftInspector = ctrl && shift && (k === 73 || k === 74 || k === 67 || k === 83 || k === 69);
        var ctrlViewSource = ctrl && (k === 85 || k === 83 || k === 80);
        var devtoolsDirect = ctrl && (k === 71 || k === 83);

        if (f12 || ctrlShiftInspector || ctrlViewSource) {
            if (ctrl && k === 83 && isEditable()) return;
            block(e);
        }
    });

    document.addEventListener('dragstart', block);

    document.addEventListener('copy', function (e) {
        if (!isEditable()) {
            e.preventDefault();
        }
    });

    document.addEventListener('mouseup', function () {
        if (window.getSelection && !isEditable()) {
            var sel = window.getSelection();
            if (sel && sel.removeAllRanges) sel.removeAllRanges();
        }
    });

    setInterval(function () {
        var w = window.outerWidth - window.innerWidth;
        var h = window.outerHeight - window.innerHeight;
        if (w > 160 || h > 160) showWarn();
    }, 2500);
})();
