export class CommandHandler {
    constructor(sessionManager) {
        this.sessionManager = sessionManager;
    }

    async execute(commandName, sessionId, payload) {
        const handler = this.handlers[commandName];
        if (!handler) {
            throw new Error(`Unknown command: ${commandName}`);
        }

        return await handler.call(this, sessionId, payload);
    }

    handlers = {
        start_session: async (sessionId, payload) => {
            const { initial_url, mode, allowed_domains } = payload;

            let tab;
            if (mode === 'attach_current_tab') {
                const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
                tab = activeTab;
            } else {
                tab = await chrome.tabs.create({ url: initial_url || 'about:blank' });
            }

            // Create session
            this.sessionManager.createSession(sessionId, tab.id, allowed_domains);

            // Inject content scripts if not already present
            await this.injectContentScripts(tab.id);

            return { tabId: tab.id, url: tab.url };
        },

        navigate: async (sessionId, payload) => {
            const { target_url, wait_for } = payload;
            const session = this.sessionManager.getSession(sessionId);

            if (!session) {
                throw new Error(`Session not found: ${sessionId}`);
            }

            // Check domain allowlist
            const url = new URL(target_url);
            if (!this.sessionManager.isDomainAllowed(sessionId, url.hostname)) {
                throw new Error(`Domain not allowed: ${url.hostname}`);
            }

            await chrome.tabs.update(session.tabId, { url: target_url });

            // Wait for page load
            if (wait_for) {
                await this.waitForCondition(session.tabId, wait_for);
            }

            return { success: true };
        },

        fill_form: async (sessionId, payload) => {
            const { field_mappings, options } = payload;
            const session = this.sessionManager.getSession(sessionId);

            // Send to content script
            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'fill_form',
                data: { field_mappings, options }
            });

            return result;
        },

        click: async (sessionId, payload) => {
            const { locator, click_type, post_click_wait } = payload;
            const session = this.sessionManager.getSession(sessionId);

            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'click_element',
                data: { locator, click_type }
            });

            if (post_click_wait) {
                await this.waitForCondition(session.tabId, post_click_wait);
            }

            return result;
        },

        wait_for: async (sessionId, payload) => {
            const { condition_type, condition_value, timeout_ms } = payload;
            const session = this.sessionManager.getSession(sessionId);

            await this.waitForCondition(session.tabId, payload);

            return { success: true };
        },

        extract: async (sessionId, payload) => {
            const { extraction_spec } = payload;
            const session = this.sessionManager.getSession(sessionId);

            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'extract_data',
                data: { extraction_spec }
            });

            return result;
        },

        scroll: async (sessionId, payload) => {
            const session = this.sessionManager.getSession(sessionId);

            const result = await chrome.tabs.sendMessage(session.tabId, {
                action: 'scroll_page',
                data: payload
            });

            return result;
        },

        end_session: async (sessionId, payload) => {
            const { close_tab } = payload;
            const session = this.sessionManager.getSession(sessionId);

            if (close_tab) {
                await chrome.tabs.remove(session.tabId);
            }

            this.sessionManager.removeSession(sessionId);

            return { success: true };
        },

        set_cursor_visibility: async (sessionId, payload) => {
            const { visible, style } = payload;
            const session = this.sessionManager.getSession(sessionId);

            await chrome.tabs.sendMessage(session.tabId, {
                action: 'set_cursor',
                data: { visible, style }
            });

            return { success: true };
        },

        capture_screenshot: async (sessionId, payload) => {
            const session = this.sessionManager.getSession(sessionId);

            const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });

            return { screenshot: dataUrl };
        },

        monitor_login: async (sessionId, payload) => {
            // Just a placeholder to acknowledge the command
            // The actual monitoring logic would be in content script or background loop
            return { success: true };
        }
    };

    async waitForCondition(tabId, condition) {
        const { condition_type, condition_value, timeout_ms = 30000 } = condition;

        const startTime = Date.now();

        while (Date.now() - startTime < timeout_ms) {
            try {
                const result = await chrome.tabs.sendMessage(tabId, {
                    action: 'check_condition',
                    data: { condition_type, condition_value }
                });

                if (result.met) {
                    return true;
                }
            } catch (error) {
                // Tab might not be ready yet
            }

            await new Promise(resolve => setTimeout(resolve, 500));
        }

        throw new Error(`Condition timeout: ${condition_type}`);
    }

    async injectContentScripts(tabId) {
        try {
            await chrome.scripting.executeScript({
                target: { tabId },
                files: [
                    'content/dom-actions.js',
                    'content/extractor.js',
                    'content/overlay.js',
                    'content/content-script.js'
                ]
            });
        } catch (error) {
            // Scripts might already be injected
            console.log('Content scripts already injected or injection failed:', error);
        }
    }
}
