const params = new URLSearchParams(location.search)
const id = params.get('id')
const host = params.get('host') || ''
const pattern = params.get('pattern') || ''
document.getElementById('host').textContent = host

async function decide(granted) {
  await chrome.runtime.sendMessage({ type: 'vz-permission-decision', id, granted }).catch(() => {})
  window.close()
}

document.getElementById('allow').addEventListener('click', async () => {
  // Chrome shows its own confirmation for the site as well.
  const granted = await chrome.permissions.request({ origins: [pattern] }).catch(() => false)
  if (granted) await decide(true)
  else document.getElementById('status').textContent = 'Your browser did not allow access. Try again, or choose Not now to return to chat.'
})
document.getElementById('deny').addEventListener('click', () => decide(false))
