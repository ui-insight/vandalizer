class WorkflowRecorder {
    constructor(recordingId = null) {
        this.isRecording = false;
        this.recordedSteps = [];
        this.startURL = null;
        this.sessionVariables = new Map();
        this.recordingId = recordingId;
    }

    async start() {
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

        // Generate locator strategies using TargetPicker logic (reused or new instance)
        // Ensure TargetPicker is available
        if (!window.VandalizerTargetPicker) {
            console.error('[Recorder] TargetPicker not found');
            return;
        }

        const targetPicker = new window.VandalizerTargetPicker();
        const strategies = await targetPicker.generateStrategies(element);

        // Record step
        this.recordedSteps.push({
            type: 'click',
            timestamp: Date.now(),
            url: window.location.href,
            target: { strategies: strategies },
            element_tag: element.tagName,
            element_text: element.innerText?.substring(0, 50),
            description: `Click ${element.tagName.toLowerCase()}` +
                (element.innerText ? ` "${element.innerText.substring(0, 30)}"` : '')
        });

        this.updateBanner();
        await this.saveState();
    }

    async recordInput(event) {
        if (!this.isRecording) return;
        // Optional: debounce saveState if we enable input recording
    }

    async recordChange(event) {
        if (!this.isRecording) return;

        const element = event.target;

        // Ignore recorder UI
        if (element.closest('#vandalizer-recorder-banner')) return;

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

            this.recordedSteps.push({
                type: 'fill_form',
                timestamp: Date.now(),
                url: window.location.href,
                target: { strategies: strategies },
                value: isSensitive ? '{{variable_placeholder}}' : element.value,
                is_sensitive: isSensitive,
                field_name: element.name || element.id || 'unknown',
                description: `Type into ${element.name || element.id || 'field'}`
            });

            if (isSensitive) {
                this.sessionVariables.set(element.name || element.id, {
                    value: element.value,
                    type: 'string',
                    description: `Value for ${element.name || element.id}`
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
        banner.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
                <div class="recorder-status">
                    🔴 Recording <span style="margin-left:8px; font-weight:normal; opacity:0.8;">|</span> <span id="step-count" style="margin-left:8px; font-weight:bold;">${this.recordedSteps.length}</span> steps
                </div>
                <div class="recorder-actions">
                    <button id="recorder-stop">Stop</button>
                </div>
            </div>
        `;

        banner.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #222;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 2147483647;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            font-weight: 500;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            border: 1px solid rgba(255,255,255,0.1);
        `;

        document.body.appendChild(banner);

        const stopBtn = document.getElementById('recorder-stop');
        stopBtn.style.cssText = `
            background: #ef4444;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
        `;

        stopBtn.onclick = () => this.stop();
    }

    removeBanner() {
        const banner = document.getElementById('vandalizer-recorder-banner');
        if (banner) {
            banner.remove();
        }
    }

    updateBanner() {
        const counter = document.getElementById('step-count');
        if (counter) {
            counter.textContent = this.recordedSteps.length;
        }

        // Notify background script of step count update
        if (this.recordingId) {
            chrome.runtime.sendMessage({
                action: 'recording_step_added',
                recording_id: this.recordingId,
                stepCount: this.recordedSteps.length,
                step: this.recordedSteps[this.recordedSteps.length - 1]
            });
        }
    }
}

window.VandalizerRecorder = WorkflowRecorder;
