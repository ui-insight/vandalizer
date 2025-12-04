import { SessionManager } from './session-manager.js';
import { CommandHandler } from './command-handler.js';

class BrowserAutomationBackground {
    constructor() {
        this.wsConnection = null;
        this.sessionManager = new SessionManager();
        this.commandHandler = new CommandHandler(this.sessionManager);
        this.reconnectInterval = null;
        this.backendUrl = null;
        this.userToken = null;

        this.setupListeners();
    }

    setupListeners() {
        // Listen for messages from content scripts
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleContentScriptMessage(message, sender, sendResponse);
            return true; // Keep channel open for async response
        });

        // Listen for tab updates (navigation, close)
        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            this.handleTabUpdate(tabId, changeInfo, tab);
        });

        chrome.tabs.onRemoved.addListener((tabId) => {
            this.handleTabRemoved(tabId);
        });

        // Extension installation/startup
        chrome.runtime.onInstalled.addListener(() => {
            this.initialize();
        });

        chrome.runtime.onStartup.addListener(() => {
            this.initialize();
        });
    }

    async initialize() {
        // Load configuration from storage
        const config = await chrome.storage.local.get(['backendUrl', 'userToken']);
        this.backendUrl = config.backendUrl || 'ws://localhost:5000';
        this.userToken = config.userToken;

        if (this.userToken) {
            this.connectToBackend();
        }
    }

    connectToBackend() {
        if (this.wsConnection?.readyState === WebSocket.OPEN) {
            return; // Already connected
        }

        this.wsConnection = new WebSocket(`${this.backendUrl}/browser_automation/websocket/connect`);

        this.wsConnection.onopen = () => {
            console.log('[BrowserAutomation] Connected to backend');

            // Send authentication
            this.sendToBackend({
                type: 'auth',
                token: this.userToken
            });

            // Start heartbeat
            this.startHeartbeat();
        };

        this.wsConnection.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleBackendMessage(message);
        };

        this.wsConnection.onerror = (error) => {
            console.error('[BrowserAutomation] WebSocket error:', error);
        };

        this.wsConnection.onclose = () => {
            console.log('[BrowserAutomation] Disconnected from backend');
            this.scheduleReconnect();
        };
    }

    scheduleReconnect() {
        if (this.reconnectInterval) return;

        this.reconnectInterval = setInterval(() => {
            if (this.wsConnection?.readyState !== WebSocket.OPEN) {
                this.connectToBackend();
            } else {
                clearInterval(this.reconnectInterval);
                this.reconnectInterval = null;
            }
        }, 5000);
    }

    startHeartbeat() {
        setInterval(() => {
            if (this.wsConnection?.readyState === WebSocket.OPEN) {
                this.sendToBackend({ type: 'heartbeat', timestamp: Date.now() });
            }
        }, 30000); // Every 30 seconds
    }

    sendToBackend(message) {
        if (this.wsConnection?.readyState === WebSocket.OPEN) {
            this.wsConnection.send(JSON.stringify(message));
        }
    }

    async handleBackendMessage(message) {
        const { type, command_name, request_id, session_id, payload } = message;

        if (type === 'command') {
            // Execute command and send response
            try {
                const result = await this.commandHandler.execute(
                    command_name,
                    session_id,
                    payload
                );

                this.sendToBackend({
                    type: 'response',
                    command_name,
                    request_id,
                    session_id,
                    payload: { status: 'success', data: result },
                    timestamp: Date.now()
                });
            } catch (error) {
                this.sendToBackend({
                    type: 'response',
                    command_name,
                    request_id,
                    session_id,
                    payload: {
                        status: 'error',
                        message: error.message,
                        stack: error.stack
                    },
                    timestamp: Date.now()
                });
            }
        }
    }

    async handleContentScriptMessage(message, sender, sendResponse) {
        const { action, data } = message;

        switch (action) {
            case 'element_picked':
                // User picked an element for selector generation
                this.handleElementPicked(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'login_detected':
                // Content script detected successful login
                this.handleLoginDetected(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'extraction_complete':
                // Content script finished extracting data
                this.handleExtractionComplete(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'connect_to_backend':
                this.initialize();
                break;

            case 'disconnect_from_backend':
                if (this.wsConnection) {
                    this.wsConnection.close();
                }
                break;

            case 'get_connection_status':
                sendResponse({
                    connected: this.wsConnection?.readyState === WebSocket.OPEN
                });
                break;

            case 'get_active_sessions':
                sendResponse({
                    sessions: Array.from(this.sessionManager.sessions.values())
                });
                break;
        }
    }

    handleTabUpdate(tabId, changeInfo, tab) {
        if (changeInfo.status === 'complete') {
            const session = this.sessionManager.getSessionByTabId(tabId);
            if (session) {
                // Send navigation_complete event
                this.sendToBackend({
                    type: 'event',
                    event_name: 'navigation_complete',
                    session_id: session.id,
                    payload: {
                        url: tab.url,
                        title: tab.title
                    },
                    timestamp: Date.now()
                });
            }
        }
    }

    handleTabRemoved(tabId) {
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            // Tab closed unexpectedly
            this.sendToBackend({
                type: 'event',
                event_name: 'session_failed',
                session_id: session.id,
                payload: {
                    reason: 'Tab closed by user'
                },
                timestamp: Date.now()
            });

            this.sessionManager.removeSession(session.id);
        }
    }

    handleElementPicked(data, tabId) {
        // Forward to backend for element picker feature
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            this.sendToBackend({
                type: 'event',
                event_name: 'element_picked',
                session_id: session.id,
                payload: data,
                timestamp: Date.now()
            });
        }
    }

    handleLoginDetected(data, tabId) {
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            this.sendToBackend({
                type: 'event',
                event_name: 'login_state_changed',
                session_id: session.id,
                payload: {
                    is_logged_in: true,
                    ...data
                },
                timestamp: Date.now()
            });
        }
    }

    handleExtractionComplete(data, tabId) {
        const session = this.sessionManager.getSessionByTabId(tabId);
        if (session) {
            this.sendToBackend({
                type: 'event',
                event_name: 'extraction_result',
                session_id: session.id,
                payload: data,
                timestamp: Date.now()
            });
        }
    }
}

// Initialize
const browserAutomation = new BrowserAutomationBackground();
