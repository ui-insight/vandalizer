// ============================================================================
// Vandalizer Browser Automation - Service Worker (Socket.IO Version)
// ============================================================================

// Load Socket.IO library FIRST (must be at top)
importScripts('../lib/socket.io.min.js');

// ============================================================================
// Session Manager (inline to avoid module issues)
// ============================================================================
class SessionManager {
    constructor() {
        this.sessions = new Map();
    }

    createSession(sessionId, tabId) {
        this.sessions.set(sessionId, {
            id: sessionId,
            tabId: tabId,
            created: Date.now()
        });
        return this.sessions.get(sessionId);
    }

    getSession(sessionId) {
        return this.sessions.get(sessionId);
    }

    getSessionByTabId(tabId) {
        for (const session of this.sessions.values()) {
            if (session.tabId === tabId) {
                return session;
            }
        }
        return null;
    }

    removeSession(sessionId) {
        this.sessions.delete(sessionId);
    }
}

// ============================================================================
// Command Handler (inline to avoid module issues)
// ============================================================================
class CommandHandler {
    constructor(sessionManager) {
        this.sessionManager = sessionManager;
    }

    async execute(commandName, sessionId, payload) {
        console.log(`[CommandHandler] Executing ${commandName} for session ${sessionId}`);

        switch (commandName) {
            case 'start_session':
                return await this.handleStartSession(sessionId, payload);
            case 'end_session':
                return await this.handleEndSession(sessionId, payload);
            case 'navigate':
                return await this.handleNavigate(sessionId, payload);
            case 'click':
                return await this.handleClick(sessionId, payload);
            case 'extract':
                return await this.handleExtract(sessionId, payload);
            case 'get_page_state':
                return await this.handleGetPageState(sessionId, payload);
            case 'wait_for':
                return await this.handleWaitFor(sessionId, payload);
            case 'smart_action':
                return await this.handleSmartAction(sessionId, payload);
            default:
                throw new Error(`Unknown command: ${commandName}`);
        }
    }

    async handleStartSession(sessionId, payload) {
        console.log(`[CommandHandler] Starting session ${sessionId}`, payload);
        const session = this.sessionManager.createSession(sessionId, null);

        // If initial_url provided, navigate to it
        if (payload.initial_url) {
            const tab = await chrome.tabs.create({ url: payload.initial_url });
            session.tabId = tab.id;
            return { sessionId, tabId: tab.id, url: tab.url };
        }

        return { sessionId, ready: true };
    }

    async handleEndSession(sessionId, payload) {
        console.log(`[CommandHandler] Ending session ${sessionId}`);
        const session = this.sessionManager.getSession(sessionId);
        if (session?.tabId) {
            await chrome.tabs.remove(session.tabId);
        }
        this.sessionManager.removeSession(sessionId);
        return { sessionId, ended: true };
    }

    async handleSmartAction(sessionId, payload) {
        console.log(`[CommandHandler] Smart action for session ${sessionId}:`, payload.instruction);
        // For now, just return success - smart actions would need LLM integration
        return { success: true, instruction: payload.instruction, message: 'Smart actions not yet implemented' };
    }

    async handleNavigate(sessionId, payload) {
        const session = this.sessionManager.getSession(sessionId);
        if (!session) {
            session = this.sessionManager.createSession(sessionId, null);
        }

        // Support both 'url' and 'target_url' field names
        const targetUrl = payload.url || payload.target_url;
        if (!targetUrl) {
            throw new Error('No URL provided for navigation');
        }

        console.log(`[CommandHandler] Navigating to: ${targetUrl}`);
        const tab = await chrome.tabs.create({ url: targetUrl });
        session.tabId = tab.id;

        // Wait for the page to finish loading
        await new Promise((resolve) => {
            const listener = (tabId, changeInfo) => {
                if (tabId === tab.id && changeInfo.status === 'complete') {
                    chrome.tabs.onUpdated.removeListener(listener);
                    resolve();
                }
            };
            chrome.tabs.onUpdated.addListener(listener);

            // Timeout after 30 seconds
            setTimeout(() => {
                chrome.tabs.onUpdated.removeListener(listener);
                resolve();
            }, 30000);
        });

        // Get updated tab info after loading
        const updatedTab = await chrome.tabs.get(tab.id);

        // Verify the tab navigated to a valid URL (not still on chrome://)
        if (updatedTab.url.startsWith('chrome://') || updatedTab.url.startsWith('chrome-extension://')) {
            throw new Error(`Navigation failed: Tab still on ${updatedTab.url}`);
        }

        console.log(`[CommandHandler] Navigation complete: ${updatedTab.url}`);
        return { tabId: updatedTab.id, url: updatedTab.url, title: updatedTab.title };
    }

    async handleClick(sessionId, payload) {
        const session = this.sessionManager.getSession(sessionId);
        if (!session?.tabId) {
            throw new Error('No active tab for session');
        }

        // Get current URL to detect navigation
        const tabBefore = await chrome.tabs.get(session.tabId);
        const urlBefore = tabBefore.url;

        // Send message to content script to click element
        // Pass the full payload which includes locator and click_type
        const result = await chrome.tabs.sendMessage(session.tabId, {
            action: 'click_element',
            data: payload
        });

        // Wait briefly to detect if navigation occurred
        await new Promise(resolve => setTimeout(resolve, 500));

        const tabAfter = await chrome.tabs.get(session.tabId);

        // If URL changed or page is loading, wait for navigation to complete
        if (tabAfter.url !== urlBefore || tabAfter.status === 'loading') {
            console.log(`[CommandHandler] Click triggered navigation, waiting for page load...`);

            await new Promise((resolve) => {
                const listener = (tabId, changeInfo) => {
                    if (tabId === session.tabId && changeInfo.status === 'complete') {
                        chrome.tabs.onUpdated.removeListener(listener);
                        resolve();
                    }
                };
                chrome.tabs.onUpdated.addListener(listener);

                // Timeout after 30 seconds
                setTimeout(() => {
                    chrome.tabs.onUpdated.removeListener(listener);
                    resolve();
                }, 30000);
            });

            const tabFinal = await chrome.tabs.get(session.tabId);
            console.log(`[CommandHandler] Navigation complete after click: ${tabFinal.url}`);
        }

        return result;
    }

    async handleExtract(sessionId, payload) {
        const session = this.sessionManager.getSession(sessionId);
        if (!session?.tabId) {
            throw new Error('No active tab for session');
        }

        console.log('[CommandHandler] Extract payload:', JSON.stringify(payload, null, 2));

        // Send message to content script to extract data
        // Pass the full payload which includes extraction_spec
        const result = await chrome.tabs.sendMessage(session.tabId, {
            action: 'extract_data',
            data: payload
        });

        console.log('[CommandHandler] Extract result:', JSON.stringify(result, null, 2));

        return result;
    }

    async handleGetPageState(sessionId, payload) {
        const session = this.sessionManager.getSession(sessionId);
        if (!session?.tabId) {
            throw new Error('No active tab for session');
        }

        // Get tab info
        const tab = await chrome.tabs.get(session.tabId);

        // Check if URL is accessible (not chrome://, chrome-extension://, etc.)
        if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
            throw new Error(`Cannot access a ${tab.url.split(':')[0]}:// URL`);
        }

        // Get page HTML via scripting API
        const results = await chrome.scripting.executeScript({
            target: { tabId: session.tabId },
            func: () => {
                return {
                    html: document.documentElement.outerHTML,
                    body: document.body.innerText,
                    title: document.title,
                    url: window.location.href
                };
            }
        });

        const pageData = results[0]?.result || {};

        return {
            url: tab.url,
            title: tab.title,
            html: pageData.html || '',
            bodyText: pageData.body || '',
            ...pageData
        };
    }

    async handleWaitFor(sessionId, payload) {
        const session = this.sessionManager.getSession(sessionId);
        if (!session?.tabId) {
            throw new Error('No active tab for session');
        }

        const { condition_type, condition_value, timeout_ms = 5000 } = payload;

        if (!condition_type || !condition_value) {
            throw new Error(`Invalid wait_for parameters: condition_type=${condition_type}, condition_value=${condition_value}`);
        }

        console.log(`[CommandHandler] Waiting for ${condition_type}: ${condition_value} (timeout: ${timeout_ms}ms)`);

        // Poll for the condition
        const startTime = Date.now();
        const pollInterval = 200; // Check every 200ms

        while (Date.now() - startTime < timeout_ms) {
            try {
                const results = await chrome.scripting.executeScript({
                    target: { tabId: session.tabId },
                    func: (conditionType, conditionValue) => {
                        if (conditionType === 'element_present') {
                            return document.querySelector(conditionValue) !== null;
                        } else if (conditionType === 'element_visible') {
                            const el = document.querySelector(conditionValue);
                            if (!el) return false;
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0 && el.offsetParent !== null;
                        }
                        return false;
                    },
                    args: [condition_type, condition_value]
                });

                if (results[0]?.result === true) {
                    console.log(`[CommandHandler] Condition met: ${condition_type}`);
                    return { success: true, condition_met: true, elapsed_ms: Date.now() - startTime };
                }
            } catch (error) {
                console.error(`[CommandHandler] Error checking condition:`, error);
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, pollInterval));
        }

        // Timeout
        throw new Error(`Timeout waiting for ${condition_type}: ${condition_value}`);
    }
}

// ============================================================================
// Main Browser Automation Background Service
// ============================================================================
class BrowserAutomationBackground {
    constructor() {
        this.socket = null;
        this.sessionManager = new SessionManager();
        this.commandHandler = new CommandHandler(this.sessionManager);
        this.heartbeatInterval = null;
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
        console.log('[BrowserAutomation] Initializing...');

        // Load configuration from storage
        const config = await chrome.storage.local.get(['backendUrl', 'userToken']);
        this.backendUrl = config.backendUrl || 'http://localhost:5003';
        this.userToken = config.userToken;

        console.log(`[BrowserAutomation] Config loaded: URL=${this.backendUrl}, HasToken=${!!this.userToken}`);

        if (this.userToken) {
            this.connectToBackend();
        } else {
            console.warn('[BrowserAutomation] ⚠️  No API token found. Please configure in extension popup.');
        }
    }

    connectToBackend() {
        if (this.socket?.connected) {
            console.log('[BrowserAutomation] Already connected');
            return;
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
            console.log('[BrowserAutomation] 🔌 Socket connected, waiting for authentication...');
        });

        // Authentication successful
        this.socket.on('connected', (data) => {
            console.log(`[BrowserAutomation] ✅ Authenticated as: ${data.user_id}`);
            this.startHeartbeat();
        });

        // Handle commands from backend
        this.socket.on('command', (message) => {
            console.log('[BrowserAutomation] 📨 Received command:', message);
            this.handleBackendMessage(message);
        });

        // Handle recording control events
        this.socket.on('start_recording', (data) => {
            console.log('[BrowserAutomation] 🔴 Start recording:', data.recording_id);
            // Send to all tabs (the content script will start recording)
            chrome.tabs.query({}, (tabs) => {
                console.log(`[BrowserAutomation] Broadcasting start_recording to ${tabs.length} tabs`);
                tabs.forEach(tab => {
                    // Skip extension pages and chrome:// URLs
                    if (!tab.url.startsWith('chrome://') && !tab.url.startsWith('chrome-extension://')) {
                        console.log(`[BrowserAutomation] Sending to tab ${tab.id}: ${tab.url}`);
                        chrome.tabs.sendMessage(tab.id, {
                            action: 'start_recording',
                            recording_id: data.recording_id
                        }, (response) => {
                            if (chrome.runtime.lastError) {
                                console.log(`[BrowserAutomation] Error sending to tab ${tab.id}:`, chrome.runtime.lastError.message);
                            } else {
                                console.log(`[BrowserAutomation] ✅ Successfully sent to tab ${tab.id}, response:`, response);
                            }
                        });
                    }
                });
            });
        });

        this.socket.on('stop_recording', (data) => {
            console.log('[BrowserAutomation] ⏹️  Stop recording:', data.recording_id);
            // Send to all tabs
            chrome.tabs.query({}, (tabs) => {
                console.log(`[BrowserAutomation] Broadcasting stop_recording to ${tabs.length} tabs`);
                tabs.forEach(tab => {
                    if (!tab.url.startsWith('chrome://') && !tab.url.startsWith('chrome-extension://')) {
                        console.log(`[BrowserAutomation] Sending stop to tab ${tab.id}: ${tab.url}`);
                        chrome.tabs.sendMessage(tab.id, {
                            action: 'stop_recording',
                            recording_id: data.recording_id
                        }, (response) => {
                            if (chrome.runtime.lastError) {
                                console.log(`[BrowserAutomation] Error sending to tab ${tab.id}:`, chrome.runtime.lastError.message);
                            } else {
                                console.log(`[BrowserAutomation] ✅ Successfully sent stop to tab ${tab.id}, response:`, response);
                            }
                        });
                    }
                });
            });
        });

        // Heartbeat acknowledgment
        this.socket.on('heartbeat_ack', (data) => {
            // Silent - heartbeat working
        });

        // Connection error
        this.socket.on('connect_error', (error) => {
            console.error('[BrowserAutomation] ❌ Connection error:', error.message);
            if (error.message && error.message.includes('Invalid')) {
                console.error('[BrowserAutomation] 🔑 Invalid API token - please update in extension settings');
            }
        });

        // Disconnected
        this.socket.on('disconnect', (reason) => {
            console.log(`[BrowserAutomation] 🔌 Disconnected: ${reason}`);
        });

        // Reconnection attempt
        this.socket.on('reconnect_attempt', (attemptNumber) => {
            console.log(`[BrowserAutomation] 🔄 Reconnection attempt #${attemptNumber}...`);
        });

        // Reconnected
        this.socket.on('reconnect', (attemptNumber) => {
            console.log(`[BrowserAutomation] ✅ Reconnected after ${attemptNumber} attempts`);
        });
    }

    startHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }

        this.heartbeatInterval = setInterval(() => {
            if (this.socket?.connected) {
                this.socket.emit('message', {
                    type: 'heartbeat',
                    timestamp: Date.now()
                });
            }
        }, 30000); // Every 30 seconds
    }

    sendToBackend(message) {
        if (this.socket?.connected) {
            console.log('[BrowserAutomation] 📤 Sending to backend:', message.type, message.request_id);
            this.socket.emit('message', message);
        } else {
            console.warn('[BrowserAutomation] ⚠️  Cannot send message: Not connected');
        }
    }

    async handleBackendMessage(message) {
        const { type, command_name, request_id, session_id, payload } = message;

        if (type === 'command') {
            try {
                const result = await this.commandHandler.execute(
                    command_name,
                    session_id,
                    payload
                );

                console.log(`[BrowserAutomation] ✅ Command '${command_name}' succeeded, sending response...`);
                this.sendToBackend({
                    type: 'response',
                    command_name,
                    request_id,
                    session_id,
                    payload: { status: 'success', data: result },
                    timestamp: Date.now()
                });
            } catch (error) {
                console.error('[BrowserAutomation] ❌ Command failed:', error);
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
                this.handleElementPicked(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'login_detected':
                this.handleLoginDetected(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'extraction_complete':
                this.handleExtractionComplete(data, sender.tab.id);
                sendResponse({ success: true });
                break;

            case 'connect_to_backend':
                await this.initialize();
                sendResponse({ success: true, connected: this.socket?.connected });
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

            case 'recording_step_added':
                // Forward step to backend via Socket.IO
                console.log('[BrowserAutomation] Recording step added:', message.stepCount);
                if (this.socket?.connected) {
                    this.socket.emit('recording_step_added', {
                        recording_id: message.recording_id,
                        step: message.step
                    });
                }
                sendResponse({ success: true });
                break;

            case 'recording_complete':
                // Save recording and notify backend
                console.log('[BrowserAutomation] Recording complete:', message.recording_id);
                if (this.socket?.connected) {
                    this.socket.emit('recording_complete', {
                        recording_id: message.recording_id,
                        steps: message.steps,
                        variables: message.variables
                    });
                }
                this.handleRecordingComplete(message.recording_id, message.steps, message.variables);
                sendResponse({ success: true });
                break;

            default:
                sendResponse({ error: 'Unknown action' });
        }
    }

    handleRecordingComplete(recordingId, steps, variables) {
        console.log('[BrowserAutomation] Recording complete. Steps:', steps.length);

        // Use provided recording ID or generate new one
        recordingId = recordingId || ('rec_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));

        // Store recording temporarily in chrome.storage for backup
        chrome.storage.local.set({
            [`recording_${recordingId}`]: {
                id: recordingId,
                steps: steps,
                variables: variables,
                created: Date.now()
            }
        });

        console.log('[BrowserAutomation] Recording saved locally with ID:', recordingId);
        // Note: recording_complete is already sent to backend via socket.emit in handleContentScriptMessage
    }

    handleTabUpdate(tabId, changeInfo, tab) {
        if (changeInfo.status === 'complete') {
            const session = this.sessionManager.getSessionByTabId(tabId);
            if (session) {
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

// ============================================================================
// Initialize
// ============================================================================
console.log('[BrowserAutomation] Service worker loading...');
const browserAutomation = new BrowserAutomationBackground();
console.log('[BrowserAutomation] Service worker ready!');
