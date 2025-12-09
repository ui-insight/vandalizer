// Load Socket.IO client library from CDN
// IMPORTANT: This MUST be at the top of the file
importScripts('https://cdn.socket.io/4.8.1/socket.io.min.js');

import { SessionManager } from './session-manager.js';
import { CommandHandler } from './command-handler.js';

class BrowserAutomationBackground {
    constructor() {
        this.socket = null;  // Changed from wsConnection to socket
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
        // Changed default from ws://localhost:5000 to http://localhost:5003
        this.backendUrl = config.backendUrl || 'http://localhost:5003';
        this.userToken = config.userToken;

        if (this.userToken) {
            this.connectToBackend();
        } else {
            console.warn('[BrowserAutomation] No user token found. Please configure the extension.');
        }
    }

    connectToBackend() {
        if (this.socket?.connected) {
            return; // Already connected
        }

        console.log(`[BrowserAutomation] Connecting to ${this.backendUrl}/browser_automation...`);

        // Create Socket.IO connection
        this.socket = io(`${this.backendUrl}/browser_automation`, {
            auth: {
                token: this.userToken
            },
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 5000,
            reconnectionAttempts: Infinity
        });

        // Connection opened
        this.socket.on('connect', () => {
            console.log('[BrowserAutomation] Socket connected, waiting for authentication...');
        });

        // Authentication successful
        this.socket.on('connected', (data) => {
            console.log('[BrowserAutomation] ✅ Authenticated as:', data.user_id);
            // Start heartbeat after successful authentication
            this.startHeartbeat();
        });

        // Handle commands from backend
        this.socket.on('command', (message) => {
            this.handleBackendMessage(message);
        });

        // Heartbeat acknowledgment
        this.socket.on('heartbeat_ack', (data) => {
            // Heartbeat received, connection is alive
        });

        // Connection error
        this.socket.on('connect_error', (error) => {
            console.error('[BrowserAutomation] ❌ Connection error:', error.message);
            if (error.message.includes('Invalid token')) {
                console.error('[BrowserAutomation] Please check your API token in extension settings');
            }
        });

        // Disconnected
        this.socket.on('disconnect', (reason) => {
            console.log('[BrowserAutomation] Disconnected:', reason);
            // Socket.IO will automatically reconnect
        });

        // Reconnection attempt
        this.socket.on('reconnect_attempt', (attemptNumber) => {
            console.log(`[BrowserAutomation] Reconnection attempt #${attemptNumber}...`);
        });

        // Reconnected
        this.socket.on('reconnect', (attemptNumber) => {
            console.log(`[BrowserAutomation] ✅ Reconnected after ${attemptNumber} attempts`);
        });
    }

    startHeartbeat() {
        // Clear any existing heartbeat
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }

        this.heartbeatInterval = setInterval(() => {
            if (this.socket?.connected) {
                this.sendToBackend({
                    type: 'heartbeat',
                    timestamp: Date.now()
                });
            }
        }, 30000); // Every 30 seconds
    }

    sendToBackend(message) {
        if (this.socket?.connected) {
            this.socket.emit('message', message);
        } else {
            console.warn('[BrowserAutomation] Cannot send message: Not connected');
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
                sendResponse({ success: true });
                break;

            case 'disconnect_from_backend':
                if (this.socket) {
                    this.socket.disconnect();
                }
                sendResponse({ success: true });
                break;

            case 'get_connection_status':
                sendResponse({
                    connected: this.socket?.connected || false,
                    backendUrl: this.backendUrl,
                    hasToken: !!this.userToken
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
