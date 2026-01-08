class RepairUI {
    constructor() {
        this.isActive = false;
        this.overlay = null;
        this.onRepairComplete = null;
    }

    start(repairRequest, callback) {
        this.isActive = true;
        this.onRepairComplete = callback;
        const { targetDescription, oldStrategies } = repairRequest;

        // Create overlay
        this.overlay = document.createElement('div');
        this.overlay.id = 'vandalizer-repair-overlay';
        this.overlay.innerHTML = `
            <div class="repair-banner">
                <div class="repair-header">
                    <span class="repair-icon">🔧</span>
                    <h3>Action Failed: Element Not Found</h3>
                </div>
                <p>I couldn't find <strong>"${targetDescription || 'the target element'}"</strong>.</p>
                <p>Please click the correct element on the page to teach me.</p>
                <div class="repair-actions">
                    <button id="repair-cancel">Cancel Repair</button>
                    <button id="repair-start-picker" class="primary">Select Element</button>
                </div>
            </div>
        `;

        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            #vandalizer-repair-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.7);
                z-index: 2147483646; /* High z-index */
                display: flex;
                justify-content: center;
                align-items: center;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .repair-banner {
                background: white;
                padding: 24px;
                border-radius: 12px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.5);
                max-width: 400px;
                width: 90%;
                text-align: center;
            }
            .repair-header {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                margin-bottom: 16px;
                color: #ef4444;
            }
            .repair-header h3 { margin: 0; }
            .repair-icon { font-size: 24px; }
            .repair-actions {
                display: flex;
                gap: 12px;
                justify-content: center;
                margin-top: 24px;
            }
            .repair-actions button {
                padding: 8px 16px;
                border: 1px solid #ccc;
                background: white;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
            }
            .repair-actions button.primary {
                background: #2563eb;
                color: white;
                border-color: #2563eb;
            }
            .repair-actions button:hover { opacity: 0.9; transform: translateY(-1px); }
        `;
        this.overlay.appendChild(style);
        document.body.appendChild(this.overlay);

        // Bind events
        document.getElementById('repair-cancel').onclick = () => this.cancel();
        document.getElementById('repair-start-picker').onclick = () => this.startPicker();
    }

    startPicker() {
        // Hide repair overlay but keep active state
        this.overlay.style.display = 'none';

        // Use existing TargetPicker
        if (window.VandalizerTargetPicker) {
            const picker = new window.VandalizerTargetPicker();
            picker.start((strategies) => {
                // Determine confidence (simple heuristic for now)
                // User explicitly picked it, so it's high confidence
                const result = {
                    success: true,
                    newStrategies: strategies,
                    timestamp: Date.now()
                };

                this.complete(result);
            });
        } else {
            console.error('TargetPicker not found during repair');
            this.cancel();
        }
    }

    complete(result) {
        this.isActive = false;
        if (this.overlay) this.overlay.remove();

        if (this.onRepairComplete) {
            this.onRepairComplete(result);
        }
    }

    cancel() {
        this.isActive = false;
        if (this.overlay) this.overlay.remove();

        if (this.onRepairComplete) {
            this.onRepairComplete({ success: false, reason: 'user_cancelled' });
        }
    }
}

window.VandalizerRepairUI = RepairUI;
