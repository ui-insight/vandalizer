// Main content script - coordinates between background and page
class BrowserAutomationContent {
    constructor() {
        this.overlay = new OverlayManager();
        this.domActions = new DOMActions();
        this.extractor = new DataExtractor();
        this.sessionDetector = null;

        this.setupListeners();
        this.checkActiveRecording();
        this.startSessionMonitoring(); // Start passive monitoring
    }

    startSessionMonitoring() {
        // Run check immediately
        this.checkLogoutState();

        // And on navigation/URL change
        let lastUrl = location.href;
        new MutationObserver(() => {
            const url = location.href;
            if (url !== lastUrl) {
                lastUrl = url;
                this.checkLogoutState();
            }
        }).observe(document, { subtree: true, childList: true });

        // Also listen for history API
        window.addEventListener('popstate', () => this.checkLogoutState());
    }

    checkLogoutState() {
        // Heuristic: Check if we are on a login page
        const url = window.location.href.toLowerCase();
        const title = document.title.toLowerCase();

        const loginIndicators = [
            '/login', '/signin', '/auth/login',
            'duosecurity.com', 'shibboleth', '/saml/', '/adfs/', '/cas/login'
        ];

        const isLoginPage = loginIndicators.some(indicator => url.includes(indicator)) ||
            (title.includes('sign in') || title.includes('log in'));

        if (isLoginPage) {
            console.log('[ContentScript] Login page detected:', url);
            chrome.runtime.sendMessage({
                action: 'session_expired',
                data: {
                    url: url,
                    title: document.title,
                    timestamp: Date.now()
                }
            });
        }
    }

    async checkActiveRecording() {
        // Check if there's an active recording when page loads
        const result = await chrome.storage.local.get(['active_recording_id']);
        if (result.active_recording_id && window.VandalizerRecorder) {
            console.log('[ContentScript] Resuming recording on page load:', result.active_recording_id);
            this.recorder = new window.VandalizerRecorder(result.active_recording_id, this.overlay);
            this.recorder.start();
        }
    }

    setupListeners() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleMessage(message, sender, sendResponse);
            return true; // Async response
        });
    }

    async handleMessage(message, sender, sendResponse) {
        const { action, data } = message;

        try {
            let result;

            switch (action) {
                case 'fill_form':
                    result = await this.fillForm(data);
                    break;

                case 'click_element':
                    result = await this.clickElement(data);
                    break;

                case 'extract_data':
                    result = await this.extractData(data);
                    break;

                case 'scroll_page':
                    result = await this.scrollPage(data);
                    break;

                case 'check_condition':
                    result = await this.checkCondition(data);
                    break;

                case 'set_cursor':
                    this.overlay.setCursor(data.visible, data.style);
                    result = { success: true };
                    break;

                case 'enable_element_picker':
                    this.overlay.enableElementPicker((element) => {
                        chrome.runtime.sendMessage({
                            action: 'element_picked',
                            data: this.domActions.generateSelector(element)
                        });
                    });
                    result = { success: true };
                    break;

                case 'start_target_picker':
                    // New interactive picker
                    if (window.VandalizerTargetPicker) {
                        const picker = new window.VandalizerTargetPicker();
                        picker.start((strategies) => {
                            // Send strategies back to background/server
                            // We can use the callback_url provided in data
                            if (data.callback_url) {
                                // We can't hit the server directly comfortably from here due to Auth headers usually needed
                                // So we send back to background script which can relay, or just respond to this message if it was long-lived?
                                // Actually better to send a message to background which handles the API call
                                chrome.runtime.sendMessage({
                                    action: 'target_picked',
                                    strategies: strategies,
                                    step_id: data.step_id,
                                    callback_url: data.callback_url
                                });
                            }
                        });
                        result = { success: true, status: 'picker_started' };
                    } else {
                        throw new Error('TargetPicker not loaded');
                    }
                    break;

                case 'start_repair_mode':
                    // Self-healing repair UI
                    if (window.VandalizerRepairUI) {
                        const repairUI = new window.VandalizerRepairUI();
                        repairUI.start(data.repairRequest, (repairResult) => {
                            // Send repair result back to backend
                            chrome.runtime.sendMessage({
                                action: 'repair_completed',
                                sessionId: data.sessionId,
                                stepId: data.stepId,
                                repairResult: repairResult
                            });
                        });
                        result = { success: true, status: 'repair_mode_started' };
                    } else {
                        throw new Error('RepairUI not loaded');
                    }
                    break;

                case 'start_recording':
                    if (window.VandalizerRecorder) {
                        console.log('[ContentScript] Starting recording with ID:', message.recording_id);
                        // Store recording ID so it persists across page navigations
                        await chrome.storage.local.set({ active_recording_id: message.recording_id });
                        this.recorder = new window.VandalizerRecorder(message.recording_id, this.overlay);
                        this.recorder.start(message.external_variables || []);
                        result = { success: true, status: 'recording_started' };
                    } else {
                        throw new Error('Recorder not loaded');
                    }
                    break;

                case 'stop_recording':
                    if (this.recorder) {
                        console.log('[ContentScript] Stopping recording');
                        this.recorder.stop();
                        this.recorder = null;
                        // Clear the active recording ID
                        await chrome.storage.local.remove('active_recording_id');
                        result = { success: true, status: 'recording_stopped' };
                    } else {
                        result = { success: false, error: 'No active recording' };
                    }
                    break;

                case 'start_session_monitoring':
                    // Start monitoring for session expiration
                    if (window.VandalizerSessionDetector) {
                        this.sessionDetector = new window.VandalizerSessionDetector();
                        this.sessionDetector.start(
                            // On session expired
                            (expiredInfo) => {
                                console.log('[ContentScript] Session expired detected, notifying background');
                                chrome.runtime.sendMessage({
                                    action: 'session_expired',
                                    sessionId: data.sessionId,
                                    expiredInfo: expiredInfo
                                });
                            },
                            // On session restored
                            (restoredInfo) => {
                                console.log('[ContentScript] Session restored detected, notifying background');
                                chrome.runtime.sendMessage({
                                    action: 'session_restored',
                                    sessionId: data.sessionId,
                                    restoredInfo: restoredInfo
                                });
                            }
                        );
                        result = { success: true, status: 'monitoring_started' };
                    } else {
                        throw new Error('SessionDetector not loaded');
                    }
                    break;

                case 'stop_session_monitoring':
                    if (this.sessionDetector) {
                        this.sessionDetector.stop();
                        this.sessionDetector = null;
                        result = { success: true, status: 'monitoring_stopped' };
                    } else {
                        result = { success: false, error: 'No active monitoring' };
                    }
                    break;

                case 'check_session_state':
                    // Manual check if logged out
                    if (this.sessionDetector) {
                        result = {
                            success: true,
                            loggedOut: this.sessionDetector.isLoggedOut(),
                            currentState: this.sessionDetector.lastState
                        };
                    } else {
                        // Create temporary detector for one-time check
                        const tempDetector = new window.VandalizerSessionDetector();
                        result = {
                            success: true,
                            loggedOut: tempDetector.isLoggedOut()
                        };
                    }
                    break;
                    break;

                case 'get_page_content':
                    result = {
                        success: true,
                        html: document.documentElement.outerHTML,
                        title: document.title,
                        url: window.location.href
                    };
                    break;
            }

            sendResponse(result);
        } catch (error) {
            sendResponse({
                success: false,
                error: error.message,
                stack: error.stack
            });
        }
    }

    async findElement(data) {
        // Polling loop for 5000ms
        const timeoutMs = 5000;
        const startTime = Date.now();
        let lastError = null;

        while (Date.now() - startTime < timeoutMs) {
            try {
                // Support locator stack
                if (data.target_stack && window.LocatorStack) {
                    const stack = new window.LocatorStack(data.target_stack);
                    const result = await stack.findElement(100); // Short timeout for stack per attempt
                    if (result && result.element) {
                        return { element: result.element, usedStrategy: result.usedStrategy };
                    }
                }

                // Fallback to single locator
                if (data.locator) {
                    const element = this.domActions.findElement(data.locator);
                    if (element && this.domActions.isElementVisible(element)) {
                        return { element: element, usedStrategy: null };
                    }
                }
            } catch (error) {
                lastError = error;
            }

            // Wait before next attempt
            await new Promise(resolve => setTimeout(resolve, 200));
        }

        // If we get here, valid 'element not found'
        if (lastError) {
            console.error('Final findElement error:', lastError);
        }
        return null;
    }

    async fillForm(data) {
        const { field_mappings, options } = data;
        const results = [];

        for (const mapping of field_mappings) {
            // Mapping might have target_stack or locator
            // Note: Data structure for fill_form might need adjustment to support per-field stacks
            // Assuming mapping object can carry target_stack

            try {
                const findResult = await this.findElement(mapping);
                const element = findResult?.element;

                if (!element) {
                    results.push({
                        locator: mapping.locator,
                        success: false,
                        error: 'Element not found'
                    });
                    continue;
                }

                // Highlight element
                this.overlay.highlightElement(element);

                // Fill value
                if (options?.clear_before) {
                    element.value = '';
                }

                await this.domActions.typeIntoElement(
                    element,
                    mapping.value,
                    options?.typing_delay_ms || 0
                );

                results.push({
                    locator: mapping.locator,
                    success: true,
                    usedStrategy: findResult.usedStrategy
                });
            } catch (error) {
                results.push({
                    locator: mapping.locator,
                    success: false,
                    error: error.message
                });
            }
        }

        return { field_results: results };
    }

    async clickElement(data) {
        const { click_type } = data;

        const findResult = await this.findElement(data);
        const element = findResult?.element;

        if (!element) {
            throw new Error('Element not found');
        }

        // Highlight and click
        this.overlay.highlightElement(element);
        await this.domActions.clickElement(element, click_type);

        return {
            success: true,
            usedStrategy: findResult.usedStrategy
        };
    }

    async extractData(data) {
        console.log('[ContentScript] extractData received:', JSON.stringify(data, null, 2));
        const { extraction_spec } = data;

        const result = await this.extractor.extract(extraction_spec);
        console.log('[ContentScript] extractData result:', JSON.stringify(result, null, 2));

        return result;
    }

    async scrollPage(data) {
        const { direction, distance, target_locator, smooth } = data;

        if (target_locator || data.target_stack) {
            const findResult = await this.findElement(data); // Pass data directly as it contains stack/locator
            const element = findResult?.element;

            if (element) {
                element.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' });
            }
        } else {
            const scrollAmount = direction === 'down' ? distance : -distance;
            window.scrollBy({
                top: scrollAmount,
                behavior: smooth ? 'smooth' : 'auto'
            });
        }

        return { success: true };
    }

    async checkCondition(data) {
        const { condition_type, condition_value } = data;

        switch (condition_type) {
            case 'element_present':
                // For element_present, condition_value might be the locator value, OR data might have target_stack
                // If it's a simple legacy wait, condition_value is a CSS selector string.
                // If we want to wait for a stack, we need to handle that.

                if (data.target_stack) {
                    const result = await this.findElement(data);
                    return { met: !!result?.element, usedStrategy: result?.usedStrategy };
                }

                const element = this.domActions.findElement({
                    strategy: 'css',
                    value: condition_value
                });
                return { met: !!element };

            case 'element_visible':
                if (data.target_stack) {
                    const result = await this.findElement(data);
                    return {
                        met: result?.element && this.domActions.isElementVisible(result.element),
                        usedStrategy: result?.usedStrategy
                    };
                }

                const visElement = this.domActions.findElement({
                    strategy: 'css',
                    value: condition_value
                });
                return {
                    met: visElement && this.domActions.isElementVisible(visElement)
                };

            case 'url_matches':
                const regex = new RegExp(condition_value);
                return { met: regex.test(window.location.href) };

            case 'text_present':
                return { met: document.body.innerText.includes(condition_value) };

            default:
                return { met: false };
        }
    }
}

// Initialize
const browserAutomationContent = new BrowserAutomationContent();
