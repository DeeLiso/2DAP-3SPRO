(function () {
    try {
        // Dark mode is the default look for the whole app. The settings page
        // toggle still works and writes '0' to opt back out.
        var stored = localStorage.getItem('darkMode');
        var dark = stored === null ? true : stored === '1';
        var root = document.documentElement;
        root.classList.toggle('dark', dark);
        root.style.colorScheme = dark ? 'dark' : 'light';
    } catch (e) { }
})();
