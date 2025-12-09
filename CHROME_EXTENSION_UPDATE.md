# Chrome Extension Update for Flask-SocketIO

## Current Issue

The extension is getting 404 errors because it's trying to connect to:
```
GET /browser_automation/websocket/connect
```

This endpoint was replaced with a proper Socket.IO WebSocket connection.

## What Needs to Change

### 1. Add Socket.IO Client Library

The extension needs the Socket.IO client library. You have two options:

**Option A: Use CDN (Quick)**

Add to `chrome-extension/background/service-worker.js`:
```javascript
importScripts('https://cdn.socket.io/4.8.1/socket.io.min.js');
```

**Option B: Download Library (Better for offline)**

1. Download `socket.io.min.js` from https://cdn.socket.io/4.8.1/socket.io.min.js
2. Save to `chrome-extension/lib/socket.io.min.js`
3. Import in service worker:
```javascript
importScripts('lib/socket.io.min.js');
```

### 2. Update Connection Code

Replace the WebSocket connection code in `chrome-extension/background/service-worker.js`:

**OLD CODE (Remove):**
```javascript
this.wsConnection = new WebSocket(`${this.backendUrl}/browser_automation/websocket/connect`);
```

**NEW CODE:**
```javascript
connectToBackend() {
    if (this.socket?.connected) {
        return; // Already connected
    }

    // Connect with Socket.IO
    this.socket = io(`${this.backendUrl}/browser_automation`, {
        auth: {
            token: this.userToken
        },
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: 5000,
        reconnectionAttempts: 5
    });

    // Connection successful
    this.socket.on('connect', () => {
        console.log('[BrowserAutomation] Connected to backend');
    });

    // Authenticated successfully
    this.socket.on('connected', (data) => {
        console.log('[BrowserAutomation] Authenticated:', data);
    });

    // Handle messages from backend
    this.socket.on('command', (data) => {
        console.log('[BrowserAutomation] Received command:', data);
        this.handleBackendMessage(data);
    });

    // Connection error
    this.socket.on('connect_error', (error) => {
        console.error('[BrowserAutomation] Connection error:', error);
    });

    // Disconnected
    this.socket.on('disconnect', (reason) => {
        console.log('[BrowserAutomation] Disconnected:', reason);
    });

    // Heartbeat acknowledgment
    this.socket.on('heartbeat_ack', (data) => {
        // Heartbeat received
    });
}
```

### 3. Update Send Message Code

**OLD CODE:**
```javascript
sendToBackend(message) {
    if (this.wsConnection?.readyState === WebSocket.OPEN) {
        this.wsConnection.send(JSON.stringify(message));
    }
}
```

**NEW CODE:**
```javascript
sendToBackend(message) {
    if (this.socket?.connected) {
        this.socket.emit('message', message);
    }
}
```

### 4. Update Heartbeat

```javascript
startHeartbeat() {
    setInterval(() => {
        if (this.socket?.connected) {
            this.socket.emit('message', {
                type: 'heartbeat',
                timestamp: Date.now()
            });
        }
    }, 30000); // Every 30 seconds
}
```

### 5. Update Disconnect Code

```javascript
disconnect() {
    if (this.socket) {
        this.socket.disconnect();
        this.socket = null;
    }
}
```

## Testing the Connection

1. Generate API token from http://localhost:5003/settings
2. Configure extension with:
   - Backend URL: `http://localhost:5003`
   - User Token: `<your_generated_token>`
3. Open browser console in background script
4. Should see:
   ```
   [BrowserAutomation] Connected to backend
   [BrowserAutomation] Authenticated: {status: 'authenticated', user_id: 'your_user_id'}
   ```

## Backend Socket.IO Endpoint Details

**Namespace:** `/browser_automation`

**Authentication:** Token passed in `auth.token` during connection

**Events from Backend:**
- `connected` - Authentication successful
- `command` - Execute a browser command
- `heartbeat_ack` - Heartbeat response

**Events to Backend:**
- `message` - Send response/event/heartbeat to backend
  - `{type: 'response', request_id, payload}`
  - `{type: 'event', event_name, payload}`
  - `{type: 'heartbeat', timestamp}`

## Complete Example

```javascript
class BrowserAutomationBackground {
    constructor() {
        this.socket = null;
        this.backendUrl = null;
        this.userToken = null;
        this.setupListeners();
    }

    async initialize() {
        const config = await chrome.storage.local.get(['backendUrl', 'userToken']);
        this.backendUrl = config.backendUrl || 'http://localhost:5003';
        this.userToken = config.userToken;

        if (this.userToken) {
            this.connectToBackend();
        }
    }

    connectToBackend() {
        if (this.socket?.connected) {
            return;
        }

        this.socket = io(`${this.backendUrl}/browser_automation`, {
            auth: { token: this.userToken },
            transports: ['websocket', 'polling']
        });

        this.socket.on('connect', () => {
            console.log('✅ Connected to Vandalizer');
            this.startHeartbeat();
        });

        this.socket.on('connected', (data) => {
            console.log('✅ Authenticated:', data.user_id);
        });

        this.socket.on('command', async (data) => {
            const result = await this.executeCommand(data);
            this.socket.emit('message', {
                type: 'response',
                request_id: data.request_id,
                payload: result
            });
        });
    }

    startHeartbeat() {
        setInterval(() => {
            if (this.socket?.connected) {
                this.socket.emit('message', {
                    type: 'heartbeat',
                    timestamp: Date.now()
                });
            }
        }, 30000);
    }
}

// Load Socket.IO client library
importScripts('https://cdn.socket.io/4.8.1/socket.io.min.js');

// Initialize
const browserAutomation = new BrowserAutomationBackground();
browserAutomation.initialize();
```

## Troubleshooting

**"io is not defined" error:**
- Make sure `importScripts()` is at the TOP of service-worker.js
- Verify the Socket.IO library loaded correctly

**Connection rejected:**
- Check API token is valid
- Verify backend URL is correct
- Check browser console for authentication errors

**404 errors:**
- Make sure Flask-SocketIO is running
- Server should be started with `python run.py` (not `flask run`)
- Verify SocketIO is initialized in app/__init__.py
