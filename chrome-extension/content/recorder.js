class WorkflowRecorder {
    constructor(recordingId = null, overlay = null) {
        this.isRecording = false;
        this.recordedSteps = [];
        this.startURL = null;
        this.sessionVariables = new Map();
        this.recordingId = recordingId;
        this.overlay = overlay;

        // Extraction by Example state
        this.isExtractionMode = false;
        this.extractionExamples = [];
    }

    async start(externalVariables = []) {
        if (this.isRecording) return;

        this.isRecording = true;
        this.startURL = window.location.href;

        // Restore state if resuming
        if (this.recordingId) {
            try {
                const stateKey = `recording_state_${this.recordingId}`;
                const result = await chrome.storage.local.get([stateKey]);
                const savedState = result[stateKey];

                if (savedState) {
                    this.recordedSteps = savedState.steps || [];
                    this.sessionVariables = new Map(savedState.variables || []);
                    console.log(`[Recorder] Resumed recording with ${this.recordedSteps.length} steps`);
                } else {
                    this.recordedSteps = [];
                    this.sessionVariables = new Map();

                    // Ingest external variables (from previous workflow steps)
                    if (Array.isArray(externalVariables)) {
                        externalVariables.forEach(v => {
                            const name = typeof v === 'string' ? v : v.name;
                            const val = typeof v === 'string' ? '{{workflow_value}}' : v.value;

                            this.sessionVariables.set(name, {
                                value: val,
                                type: 'external',
                                description: 'From Workflow Context'
                            });
                        });
                        console.log('[Recorder] Ingested external variables:', this.sessionVariables);
                    }

                    // Capture initial navigation
                    await this._captureInitialNavigation();
                }
            } catch (err) {
                console.error('[Recorder] Failed to restore state:', err);
                this.recordedSteps = [];
                this.sessionVariables = new Map();
                await this._captureInitialNavigation();
            }
        } else {
            this.recordedSteps = [];
            this.sessionVariables = new Map();
            await this._captureInitialNavigation();
        }

        // Show recording banner
        this.showBanner();

        // Attach listeners
        document.addEventListener('click', this.recordClick.bind(this), true);
        document.addEventListener('input', this.recordInput.bind(this), true);
        document.addEventListener('change', this.recordChange.bind(this), true);
        document.addEventListener('focusin', this.onFocus.bind(this), true); // Suggested variables on focus

        // Navigation observer
        this.observeNavigation();

        console.log('[Recorder] Started recording');
    }

    async _captureInitialNavigation() {
        const currentUrl = window.location.href;
        console.log('[Recorder] Capturing initial navigation to:', currentUrl);

        this.recordedSteps.push({
            type: 'navigate',
            timestamp: Date.now(),
            url: currentUrl,
            description: `Navigate to ${currentUrl}`
        });

        this.updateBanner();
        await this.saveState();
    }

    async saveState() {
        if (!this.recordingId) return;

        try {
            await chrome.storage.local.set({
                [`recording_state_${this.recordingId}`]: {
                    steps: this.recordedSteps,
                    variables: Array.from(this.sessionVariables.entries())
                }
            });
        } catch (err) {
            console.error('[Recorder] Failed to save state:', err);
        }
    }

    async recordClick(event) {
        if (!this.isRecording) return;

        const element = event.target;

        // Ignore recorder UI clicks
        if (element.closest('#vandalizer-recorder-banner')) {
            return;
        }

        // Ignore clicks on variable autocomplete dropdown
        if (element.closest('#vandalizer-autocomplete')) {
            return;
        }

        // Generate locator strategies using TargetPicker logic (reused or new instance)
        // Ensure TargetPicker is available
        if (!window.VandalizerTargetPicker) {
            console.error('[Recorder] TargetPicker not found');
            return;
        }

        const targetPicker = new window.VandalizerTargetPicker();
        const strategies = await targetPicker.generateStrategies(element);

        // EXTRACTION MODE HANDLER
        if (this.isExtractionMode) {
            event.preventDefault();
            event.stopPropagation();

            if (this.overlay) {
                this.overlay.showExtractionPrompt(element, (result) => {
                    if (result.type === 'single') {
                        // Single variable extraction
                        const variableName = result.name;

                        // We use the most robust strategy for single value
                        const primaryStrategy = strategies[0] || { type: 'css', value: element.tagName };

                        this.recordedSteps.push({
                            type: 'extract',
                            timestamp: Date.now(),
                            url: window.location.href,
                            description: `Extract variable "{{${variableName}}}" from ${element.tagName}`,
                            extraction_spec: {
                                fields: [
                                    {
                                        name: variableName,
                                        locator: {
                                            strategy: primaryStrategy.type,
                                            value: primaryStrategy.value
                                        },
                                        attribute: 'innerText' // Default to innerText
                                    }
                                ]
                            },
                            // Also store target stack for robustness/self-healing if supported later
                            target: { strategies: strategies }
                        });

                        this.sessionVariables.set(variableName, {
                            type: 'string',
                            description: `Extracted from ${element.tagName}`
                        });

                        console.log(`[Recorder] Recorded single variable extraction: ${variableName}`);
                        this.updateBanner();
                        this.saveState();

                    } else {
                        // List (Example)
                        this.extractionExamples.push({
                            tag: element.tagName,
                            text: element.innerText?.substring(0, 100),
                            strategies: strategies,
                            outerHTML: element.outerHTML
                        });

                        if (this.overlay) {
                            this.overlay.addHighlight(element);
                        }
                        this.updateBanner();
                    }
                });
            }
            return;
        }

        // Record step
        // Record step
        const isDestructive = this.isDestructive(element);

        this.recordedSteps.push({
            type: 'click',
            timestamp: Date.now(),
            url: window.location.href,
            target: { strategies: strategies },
            element_tag: element.tagName,
            element_text: element.innerText?.substring(0, 50),
            destructive: isDestructive,
            description: `Click ${element.tagName.toLowerCase()}` +
                (element.innerText ? ` "${element.innerText.substring(0, 30)}"` : '') +
                (isDestructive ? ' [DESTRUCTIVE]' : '')
        });

        this.updateBanner();
        await this.saveState();
    }

    async recordInput(event) {
        if (!this.isRecording) return;

        const element = event.target;
        if (!element || (element.tagName !== 'INPUT' && element.tagName !== 'TEXTAREA')) return;

        // Check for variable trigger "{{"
        // We only care if the cursor is after "{{"
        const cursorPos = element.selectionStart;
        const textBeforeCursor = element.value.substring(0, cursorPos);

        if (textBeforeCursor.endsWith('{{')) {
            // User typed "{{", show suggestions
            const variables = Array.from(this.sessionVariables.keys());

            if (variables.length > 0 && this.overlay) {
                this.overlay.showAutocomplete(element, variables, (selectedVar) => {
                    // Start after "{{" and replace/insert
                    // Actually, we just append content or replace
                    // Simple replacement:
                    const textAfterCursor = element.value.substring(element.selectionEnd);
                    const newText = textBeforeCursor + selectedVar + '}}' + textAfterCursor;
                    element.value = newText;

                    // Move cursor after the inserted variable
                    // This might need a slight delay or just set selection
                    // element.selectionStart = element.selectionEnd = textBeforeCursor.length + selectedVar.length + 2;

                    // Trigger change event so recorder captures this as a fill_form action
                    const changeEvent = new Event('change', { bubbles: true });
                    element.dispatchEvent(changeEvent);
                });
            }
        }
    }

    async onFocus(event) {
        if (!this.isRecording) return;

        const element = event.target;
        if (!element || (element.tagName !== 'INPUT' && element.tagName !== 'TEXTAREA')) return;

        // Ignore if clicking inside recorder UI
        if (element.closest('#vandalizer-recorder-banner')) return;

        this.lastFocusedInput = element;

        const variables = Array.from(this.sessionVariables.keys());
        if (variables.length > 0 && this.overlay) {
            // "Casually suggest" - show autocomplete immediately on focus
            this.overlay.showAutocomplete(element, variables, (selectedVar) => {
                // If field is empty, just insert.
                // If not empty, maybe append? Or replace?
                // Let's assume replace if it looks like a placeholder, otherwise append.
                // Actually, safeguard: Insert at cursor or end.
                const cursorPos = element.selectionStart || element.value.length;
                const textBefore = element.value.substring(0, cursorPos);
                const textAfter = element.value.substring(cursorPos);

                // Add {{ }}
                const newText = textBefore + '{{' + selectedVar + '}}' + textAfter;
                element.value = newText;

                // Trigger change event so recorder captures this as a fill_form action
                console.log('[Recorder] Dispatching change event for variable insertion');
                const changeEvent = new Event('change', { bubbles: true });
                element.dispatchEvent(changeEvent);
                console.log('[Recorder] Change event dispatched');
            });
        }
    }
    async recordChange(event) {
        console.log('[Recorder] recordChange called, target:', event.target);
        if (!this.isRecording) {
            console.log('[Recorder] Not recording, ignoring change event');
            return;
        }

        const element = event.target;

        // Ignore recorder UI
        if (element.closest('#vandalizer-recorder-banner')) {
            console.log('[Recorder] Ignoring change on recorder UI');
            return;
        }

        const targetPicker = new window.VandalizerTargetPicker();
        const strategies = await targetPicker.generateStrategies(element);

        if (element.tagName === 'SELECT') {
            this.recordedSteps.push({
                type: 'select',
                timestamp: Date.now(),
                url: window.location.href,
                target: { strategies: strategies },
                option: element.options[element.selectedIndex]?.text,
                value: element.value,
                description: `Select "${element.options[element.selectedIndex]?.text}" from ${element.name || 'dropdown'}`
            });
        } else {
            // Input, textarea, etc.
            const isSensitive = this.promptSensitiveData(element);

            const fillFormAction = {
                type: 'fill_form',
                timestamp: Date.now(),
                url: window.location.href,
                target: { strategies: strategies },
                value: isSensitive ? '{{variable_placeholder}}' : element.value,
                is_sensitive: isSensitive,
                field_name: element.name || element.id || 'unknown',
                description: `Type into ${element.name || element.id || 'field'}`
            };
            console.log('[Recorder] Recording fill_form action:', fillFormAction);
            this.recordedSteps.push(fillFormAction);

            this.sessionVariables.set(element.name || element.id, {
                value: element.value,
                type: 'string',
                description: `Value for ${element.name || element.id}`
            });

            if (!isSensitive && element.value && this.overlay) {
                // Not sensitive, but user might want to make it a variable
                const stepIndex = this.recordedSteps.length - 1;

                this.overlay.showVariablePrompt(element, (variableName) => {
                    // User created a variable!
                    this.updateStepWithVariable(stepIndex, variableName, element.value);
                });
            }
        }



        this.updateBanner();
        await this.saveState();
    }

    observeNavigation() {
        let lastURL = window.location.href;

        this.navInterval = setInterval(async () => {
            if (window.location.href !== lastURL) {
                this.recordedSteps.push({
                    type: 'navigate',
                    timestamp: Date.now(),
                    url: window.location.href,
                    from_url: lastURL,
                    description: `Navigate to ${window.location.href}`
                });

                lastURL = window.location.href;
                this.updateBanner();
                await this.saveState();
            }
        }, 500);
    }

    promptSensitiveData(element) {
        // Check if looks like password/email/SSN field
        const name = (element.name || element.id || '').toLowerCase();
        const type = element.type?.toLowerCase();

        if (type === 'password' ||
            name.includes('password') ||
            name.includes('ssn') ||
            name.includes('credit') ||
            name.includes('card')) {
            return true;
        }
        return false;
    }

    isDestructive(element) {
        const text = (element.innerText || '').toLowerCase();
        const title = (element.title || '').toLowerCase();
        const ariaLabel = (element.getAttribute('aria-label') || '').toLowerCase();
        const classes = (element.className || '').toLowerCase();

        const keywords = ['delete', 'remove', 'destroy', 'cancel', 'discard', 'erase'];

        // Check if any keyword is present as a standalone word or significant part
        // Simple includes check for now
        return keywords.some(kw =>
            text.includes(kw) ||
            title.includes(kw) ||
            ariaLabel.includes(kw) ||
            classes.includes('danger') || // Common utility class for destructive buttons
            classes.includes('destructive')
        );
    }

    async stop() {
        this.isRecording = false;
        clearInterval(this.navInterval);

        // Remove banner
        this.removeBanner();

        // Clear the active recording ID from storage
        chrome.storage.local.remove('active_recording_id');

        // Clear saved state
        if (this.recordingId) {
            chrome.storage.local.remove(`recording_state_${this.recordingId}`);
        }

        // Send recorded steps to background script
        chrome.runtime.sendMessage({
            action: 'recording_complete',
            recording_id: this.recordingId,
            steps: this.recordedSteps,
            variables: Array.from(this.sessionVariables.entries()).map(([key, value]) => ({
                name: key,
                ...value
            }))
        });

        console.log('[Recorder] Stopped. Recorded', this.recordedSteps.length, 'steps');

        // Clear recording ID
        this.recordingId = null;
    }

    showLabelingUI() {
        // Send recorded steps to backend for labeling via background script
        chrome.runtime.sendMessage({
            action: 'recording_complete',
            steps: this.recordedSteps,
            variables: Array.from(this.sessionVariables.entries())
        });

        // Notify user
        alert('Recording stopped. Redirecting to labeling UI...');
    }

    showBanner() {
        if (document.getElementById('vandalizer-recorder-banner')) return;

        const banner = document.createElement('div');
        banner.id = 'vandalizer-recorder-banner';
        this.updateBannerContent(banner);

        banner.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(30, 30, 30, 0.95);
            color: white;
            padding: 16px;
            border-radius: 12px;
            z-index: 2147483647;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            width: 280px;
            box-sizing: border-box;
            backdrop-filter: blur(10px);
        `;

        document.body.appendChild(banner);
        this.attachBannerListeners();
    }

    updateBannerContent(banner) {
        if (this.isExtractionMode) {
            banner.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="color: #4ade80; font-weight: 600;">⚡ Extraction Mode</span>
                        <span style="opacity: 0.5;">|</span>
                        <span id="example-count" style="font-size:13px;">${this.extractionExamples.length} captured</span>
                    </div>
                </div>
                <div style="display: flex; gap: 8px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 8px;">
                    <button id="extract-done" style="flex: 1; background: #22c55e; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 13px;">Done</button>
                    <button id="extract-cancel" style="flex: 1; background: transparent; border: 1px solid #ef4444; color: #ef4444; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-weight: 500; font-size: 13px;">Cancel</button>
                </div>
            `;
        } else {
            const varCount = this.sessionVariables.size;
            const varsHtml = varCount > 0
                ? Array.from(this.sessionVariables.keys()).map(k =>
                    `<span class="vandalizer-var-chip" data-var="${k}" style="display:inline-block; background:rgba(59, 130, 246, 0.2); border:1px solid rgba(59, 130, 246, 0.4); color:#93c5fd; padding:2px 6px; border-radius:4px; font-size:11px; margin:2px; cursor:pointer;">{{${k}}}</span>`
                ).join('')
                : '<span style="opacity:0.5; font-size:11px; font-style:italic;">No variables captured yet</span>';

            banner.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 15px; margin-bottom: 12px;">
                    <div class="recorder-status" style="display: flex; align-items: center;">
                        <span style="color: #ef4444; font-size: 10px; margin-right: 6px;">●</span> 
                        <span style="font-weight: 600;">Recording</span> 
                        <span style="margin: 0 8px; opacity:0.3;">|</span> 
                        <span id="step-count" style="font-feature-settings: 'tnum';">${this.recordedSteps.length}</span> steps
                    </div>
                    <button id="recorder-stop" style="background: #ef4444; color: white; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 12px;">Stop</button>
                </div>

                <!-- Tools Panel -->
                <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px; margin-bottom: 10px;">
                    <div style="font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.5; margin-bottom: 6px;">Tools</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                        <button id="recorder-extract" style="background: #3b82f6; color: white; border: none; padding: 8px; border-radius: 6px; cursor: pointer; font-size: 12px; display: flex; align-items: center; justify-content: center; gap: 6px; font-weight:500;">
                            <span>⌖</span> Extract Data
                        </button>
                    </div>
                </div>

                <!-- Variables Panel -->
                <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                        <div style="font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.5;">Values</div>
                        <div style="font-size: 10px; opacity: 0.4;">${varCount}</div>
                    </div>
                    <div id="vandalizer-vars-list" style="max-height: 80px; overflow-y: auto; margin: -2px;">
                        ${varsHtml}
                    </div>
                </div>
            `;
        }
    }

    attachBannerListeners() {
        const banner = document.getElementById('vandalizer-recorder-banner');
        if (!banner) return;

        if (this.isExtractionMode) {
            document.getElementById('extract-done')?.addEventListener('click', () => this.finishExtraction());
            document.getElementById('extract-cancel')?.addEventListener('click', () => this.cancelExtraction());
        } else {
            document.getElementById('recorder-extract')?.addEventListener('click', () => this.toggleExtractionMode());
            document.getElementById('recorder-stop')?.addEventListener('click', () => this.stop());

            // Variable chips
            const chips = banner.querySelectorAll('.vandalizer-var-chip');
            chips.forEach(chip => {
                chip.addEventListener('click', (e) => {
                    e.stopPropagation(); // prevent bubbling to unrelated listeners
                    const varName = chip.getAttribute('data-var');

                    if (this.lastFocusedInput && document.body.contains(this.lastFocusedInput)) {
                        // Insert into last input
                        const el = this.lastFocusedInput;
                        const val = `{{${varName}}}`;

                        // Insert at cursor
                        const start = el.selectionStart || el.value.length;
                        const end = el.selectionEnd || el.value.length;
                        el.value = el.value.substring(0, start) + val + el.value.substring(end);

                        // Visual feedback
                        el.style.transition = 'background 0.2s';
                        el.style.background = '#dbeafe'; // Light blue flash
                        setTimeout(() => el.style.background = '', 300);

                        // Trigger change event so recorder captures this as a fill_form action
                        const changeEvent = new Event('change', { bubbles: true });
                        el.dispatchEvent(changeEvent);
                    } else {
                        // Alert user
                        alert(`Variable "{{${varName}}}" selected. Click an input field to use it.`);
                    }
                });
            });
        }
    }

    updateBanner() {
        const banner = document.getElementById('vandalizer-recorder-banner');
        if (banner) {
            this.updateBannerContent(banner);
            this.attachBannerListeners();
        }

        // Notify background
        if (this.recordingId && !this.isExtractionMode) {
            chrome.runtime.sendMessage({
                action: 'recording_step_added',
                recording_id: this.recordingId,
                stepCount: this.recordedSteps.length,
                step: this.recordedSteps[this.recordedSteps.length - 1]
            });
        }
    }

    toggleExtractionMode() {
        this.isExtractionMode = true;
        this.extractionExamples = [];
        this.updateBanner();
        console.log('[Recorder] Entered Extraction Mode');
    }

    finishExtraction() {
        if (this.extractionExamples.length > 0) {
            // Save step
            const step = {
                type: 'extract_by_example',
                timestamp: Date.now(),
                url: window.location.href,
                examples: this.extractionExamples,
                description: `Extract data like ${this.extractionExamples.length} examples`
            };
            this.recordedSteps.push(step);
            console.log('[Recorder] Added extraction step:', step);
        }

        this.cancelExtraction(); // Clean up mechanism is same
    }

    cancelExtraction() {
        this.isExtractionMode = false;
        this.extractionExamples = [];
        if (this.overlay) {
            this.overlay.clearHighlights();
        }
        this.updateBanner();
        // Force save state to sync new step if added
        this.saveState();
    }

    removeBanner() {
        const banner = document.getElementById('vandalizer-recorder-banner');
        if (banner) {
            banner.remove();
        }
    }


    async updateStepWithVariable(stepIndex, variableName, originalValue) {
        if (stepIndex < 0 || stepIndex >= this.recordedSteps.length) return;

        console.log(`[Recorder] Converting step ${stepIndex} to use variable: ${variableName}`);

        const step = this.recordedSteps[stepIndex];
        step.value = `{{${variableName}}}`; // Use jinja syntax
        step.variable_name = variableName;
        step.variable_default = originalValue;

        // Add to session variables list
        this.sessionVariables.set(variableName, {
            value: originalValue,
            type: 'string',
            description: `Auto-created from recording`
        });

        // Save updated state
        this.updateBanner();
        await this.saveState();
    }
}

window.VandalizerRecorder = WorkflowRecorder;
