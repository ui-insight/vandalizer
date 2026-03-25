# Quick Start: Browser Automation Extension

The extension in this repository already uses the Socket.IO service worker shipped in `background/service-worker-socketio.js`. No manual module conversion is required.

## Load the extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `chrome-extension/` folder from this repository

## Configure it

1. Click the extension icon to open the popup
2. Set the backend URL
   Default local value: `http://localhost:5003`
3. Paste a valid user token from the Vandalizer app
4. Save the configuration

## Verify the connection

1. In `chrome://extensions`, click **Inspect views: service worker**
2. Reload the extension if the worker is not already running
3. Look for logs like:

```text
[BrowserAutomation] Connecting to http://localhost:5003/browser_automation...
[BrowserAutomation] Socket connected, waiting for authentication...
[BrowserAutomation] Authenticated as: your_user_id
```

## Troubleshooting

- `io is not defined`
  The service worker failed to load `lib/socket.io.min.js`. Reload the extension and confirm the file exists in `chrome-extension/lib/`.
- `Connection refused`
  The configured backend URL is wrong or the backend is not running.
- `Authentication failed`
  The saved token is missing, expired, or for the wrong environment.
