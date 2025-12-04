document.addEventListener('DOMContentLoaded', async () => {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const setupSection = document.getElementById('setup-section');
    const activeSection = document.getElementById('active-section');
    const setupForm = document.getElementById('setup-form');
    const disconnectBtn = document.getElementById('disconnect-btn');
    const backendUrlInput = document.getElementById('backend-url');
    const userTokenInput = document.getElementById('user-token');

    // Load saved config
    const config = await chrome.storage.local.get(['backendUrl', 'userToken', 'connected']);

    if (config.backendUrl) {
        backendUrlInput.value = config.backendUrl;
    }

    if (config.userToken) {
        userTokenInput.value = config.userToken;
    }

    // Check connection status
    checkConnectionStatus();

    // Setup form submission
    setupForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const backendUrl = backendUrlInput.value;
        const userToken = userTokenInput.value;

        // Save config
        await chrome.storage.local.set({
            backendUrl,
            userToken,
            connected: true
        });

        // Trigger connection in background script
        chrome.runtime.sendMessage({ action: 'connect_to_backend' });

        setTimeout(checkConnectionStatus, 1000);
    });

    // Disconnect button
    disconnectBtn.addEventListener('click', async () => {
        await chrome.storage.local.set({ connected: false });
        chrome.runtime.sendMessage({ action: 'disconnect_from_backend' });

        setupSection.style.display = 'block';
        activeSection.style.display = 'none';
        updateStatus('disconnected');
    });

    async function checkConnectionStatus() {
        // Ask background script for status
        chrome.runtime.sendMessage({ action: 'get_connection_status' }, (response) => {
            if (response && response.connected) {
                updateStatus('connected');
                setupSection.style.display = 'none';
                activeSection.style.display = 'block';
                loadActiveSessions();
            } else {
                updateStatus('disconnected');
                setupSection.style.display = 'block';
                activeSection.style.display = 'none';
            }
        });
    }

    function updateStatus(status) {
        if (status === 'connected') {
            statusDot.className = 'status-indicator connected';
            statusText.textContent = 'Connected';
        } else {
            statusDot.className = 'status-indicator disconnected';
            statusText.textContent = 'Disconnected';
        }
    }

    async function loadActiveSessions() {
        // Ask background for active sessions
        chrome.runtime.sendMessage({ action: 'get_active_sessions' }, (response) => {
            const sessionsList = document.getElementById('sessions-list');

            if (response && response.sessions && response.sessions.length > 0) {
                sessionsList.innerHTML = '';

                for (const session of response.sessions) {
                    const sessionEl = document.createElement('div');
                    sessionEl.className = 'session-item';
                    sessionEl.innerHTML = `
                        <strong>Session ${session.id.substring(0, 8)}</strong>
                        <span class="session-state">${session.state}</span>
                    `;
                    sessionsList.appendChild(sessionEl);
                }
            } else {
                sessionsList.innerHTML = '<p class="no-sessions">No active sessions</p>';
            }
        });
    }

    // Auto-refresh sessions every 3 seconds
    setInterval(() => {
        if (activeSection.style.display !== 'none') {
            loadActiveSessions();
        }
    }, 3000);
});
