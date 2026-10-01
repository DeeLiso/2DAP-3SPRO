(function () {
    try {
        var isBettor = /[?&]type=bettor/.test(location.search) || location.pathname.indexOf('bettor') !== -1;
        var dark;
        if (isBettor) {
            dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        } else {
            dark = localStorage.getItem('darkMode') === '1';
        }
        var root = document.documentElement;
        root.classList.toggle('dark', dark);
        root.style.colorScheme = dark ? 'dark' : 'light';
        if (isBettor && window.matchMedia) {
            var mq = window.matchMedia('(prefers-color-scheme: dark)');
            var onChange = function (e) {
                root.classList.toggle('dark', e.matches);
                root.style.colorScheme = e.matches ? 'dark' : 'light';
            };
            if (mq.addEventListener) {
                mq.addEventListener('change', onChange);
            } else if (mq.addListener) {
                mq.addListener(onChange);
            }
        }
    } catch (e) { }
})();
