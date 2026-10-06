const field = document.getElementById('sender');
const message = document.getElementById('sender-message');
let loading;
field.addEventListener('focus', () => {
  if (loading) return;
  message.textContent = 'Loading DocuSign account users…';
  loading = fetch('/api/users').then(async response => {
    const users = await response.json();
    if (!response.ok) throw new Error(users.error || 'Unable to load users');
    const list = document.getElementById('sender-options');
    list.replaceChildren(...users.map(user => {
      const option = document.createElement('option');
      option.value = user.label;
      return option;
    }));
    message.textContent = users.length ? 'Type a name or email and choose a matching sender. Clear the field for all accessible senders.' : 'No account users were returned.';
  }).catch(error => {
    message.textContent = error.message + ' Focus this field again to retry.';
    loading = null;
  });
});
