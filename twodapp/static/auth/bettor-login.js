(function () {
  const form = document.getElementById('player-login-form');
  if (!form) return;

  const errorBox = document.getElementById('player-login-error');
  const submitButton = document.getElementById('player-login-submit');
  const submitLabel = submitButton.querySelector('.login-submit-label');
  const endpoint = form.getAttribute('data-api-login');
  const csrfField = document.querySelector('[name=csrfmiddlewaretoken]');

  const showError = (message) => {
    errorBox.textContent = message;
    errorBox.hidden = false;
  };

  const clearError = () => {
    errorBox.hidden = true;
    errorBox.textContent = '';
  };

  const setLoading = (loading) => {
    submitButton.disabled = loading;
    submitLabel.textContent = loading ? 'Signing in…' : 'Sign in';
  };

  const toggle = document.querySelector('[data-password-toggle]');
  if (toggle) {
    toggle.addEventListener('click', () => {
      const input = form.querySelector('input[name=password]');
      const revealed = input.type === 'password';
      input.type = revealed ? 'text' : 'password';
      toggle.setAttribute('aria-pressed', String(revealed));
      toggle.setAttribute('aria-label', revealed ? 'Hide password' : 'Show password');
      input.focus();
    });
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearError();

    const username = form.querySelector('input[name=username]').value.trim();
    const password = form.querySelector('input[name=password]').value;

    if (!username || !password) {
      showError('Username and password are required.');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfField ? csrfField.value : ''
        },
        body: JSON.stringify({ username, password }),
        credentials: 'same-origin'
      });
      const payload = await response.json().catch(() => ({ ok: false, error: 'Unexpected server response.' }));
      if (payload && payload.ok) {
        window.location.href = payload.redirect || '/bet/?type=bettor';
        return;
      }
      showError((payload && payload.error) || 'Sign in failed. Please try again.');
      setLoading(false);
    } catch (error) {
      showError('Network error. Please try again.');
      setLoading(false);
    }
  });
})();
