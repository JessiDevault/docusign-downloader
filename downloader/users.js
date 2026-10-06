const field = document.getElementById('sender-options');
const message = document.getElementById('sender-message');
const reload = document.getElementById('reload-users');
async function loadUsers() {
  reload.disabled = true;
  message.textContent = 'Loading DocuSign account users…';
  try {
    const response = await fetch('/api/users');
    const users = await response.json();
    if (!response.ok) throw new Error(users.error || 'Unable to load users');
    const selected = field.value;
    const all = document.createElement('option');
    all.value = '';
    all.textContent = 'All accessible senders';
    field.replaceChildren(all, ...users.map(user => {
      const option = document.createElement('option');
      option.value = user.id;
      option.textContent = user.label;
      return option;
    }));
    if (selected && users.some(user => user.id === selected)) field.value = selected;
    message.textContent = users.length ? 'Choose the DocuSign user who sent the envelopes.' : 'No account users were returned.';
  } catch (error) {
    message.textContent = error.message + ' Use Reload users to retry.';
  } finally {
    reload.disabled = false;
  }
}
reload.addEventListener('click', loadUsers);
loadUsers();
