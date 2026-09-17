(() => {
  const fields = document.getElementById('inspire-fields');
  if (!fields) return;
  const choices = document.querySelectorAll('input[name="source"]');
  const update = () => {
    const selected = document.querySelector('input[name="source"]:checked');
    // Demo defaults are supplied by the server; hidden controls must not block submission.
    const isDemo = Boolean(selected && selected.value === 'demo');
    fields.hidden = isDemo;
    fields.disabled = isDemo;
  };
  choices.forEach(choice => choice.addEventListener('change', update));
  update();
})();
