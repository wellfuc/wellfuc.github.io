const themeToggle = document.querySelector('[data-theme-toggle]');
const root = document.documentElement;

const applyTheme = (theme) => {
  if (theme === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', theme);
  }
  localStorage.setItem('apphub-theme', theme);
};

const storedTheme = localStorage.getItem('apphub-theme') || 'system';
applyTheme(storedTheme);

if (themeToggle) {
  themeToggle.addEventListener('change', (event) => {
    applyTheme(event.target.value);
  });
  themeToggle.value = storedTheme;
}

const toast = document.querySelector('.toast');

const showToast = (message) => {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('active');
  setTimeout(() => toast.classList.remove('active'), 2400);
};

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    const value = button.getAttribute('data-copy');
    try {
      await navigator.clipboard.writeText(value);
      showToast('Copied to clipboard');
    } catch (error) {
      showToast('Copy failed');
    }
  });
});
