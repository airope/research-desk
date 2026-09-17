document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
  const field = document.querySelector('[name="question"]');
  field.value = button.dataset.question;
  field.focus();
}));
const workspace = document.querySelector('[data-status]');
if (workspace && workspace.dataset.poll && ['queued', 'running'].includes(workspace.dataset.status)) {
  const timer = setInterval(async () => {
    if (document.hidden || document.querySelector('input:focus, textarea:focus')) return;
    try {
      const response = await fetch(workspace.dataset.poll, {headers: {'Accept': 'application/json'}});
      if (!response.ok) return;
      const state = await response.json();
      if (state.updated_at !== workspace.dataset.updated) {
        clearInterval(timer);
        sessionStorage.setItem('research-scroll:' + location.pathname, String(window.scrollY));
        location.reload();
      }
    } catch (_) { /* Keep saved content visible when a connection is interrupted. */ }
  }, 5000);
}
const scrollKey = 'research-scroll:' + location.pathname;
const previousScroll = sessionStorage.getItem(scrollKey);
if (previousScroll !== null) {
  sessionStorage.removeItem(scrollKey);
  window.scrollTo(0, Number(previousScroll));
}
document.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => window.print()));
