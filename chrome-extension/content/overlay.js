class OverlayManager {
    constructor() {
        this.cursor = null;
        this.highlightBox = null;
        this.highlights = []; // Store multiple highlight elements
        this.elementPickerActive = false;
        this.elementPickerCallback = null;

        this.createOverlayElements();
    }

    createOverlayElements() {
        // Create cursor element
        this.cursor = document.createElement('div');
        this.cursor.id = 'vandalizer-cursor';
        this.cursor.style.cssText = `
            position: fixed;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: rgba(59, 130, 246, 0.5);
            border: 2px solid rgb(59, 130, 246);
            pointer-events: none;
            z-index: 999999;
            display: none;
            transition: all 0.1s ease;
        `;
        document.body.appendChild(this.cursor);

        // Create highlight box
        this.highlightBox = document.createElement('div');
        this.highlightBox.id = 'vandalizer-highlight';
        this.highlightBox.style.cssText = `
            position: absolute;
            border: 2px solid rgb(34, 197, 94);
            background: rgba(34, 197, 94, 0.1);
            pointer-events: none;
            z-index: 999998;
            display: none;
            transition: all 0.2s ease;
        `;
        document.body.appendChild(this.highlightBox);

        // Create variable prompt container
        this.variablePrompt = document.createElement('div');
        this.variablePrompt.id = 'vandalizer-variable-prompt';
        this.variablePrompt.style.cssText = `
            position: absolute;
            background: white;
            padding: 8px;
            border-radius: 6px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            z-index: 999999;
            display: none;
            font-family: sans-serif;
            font-size: 13px;
            border: 1px solid #e5e7eb;
            min-width: 200px;
        `;
        document.body.appendChild(this.variablePrompt);
    }

    setCursor(visible, style = {}) {
        if (visible) {
            this.cursor.style.display = 'block';
            this.trackMouse();
        } else {
            this.cursor.style.display = 'none';
        }

        // Apply custom styles
        Object.assign(this.cursor.style, style);
    }

    trackMouse() {
        document.addEventListener('mousemove', (e) => {
            if (this.cursor.style.display === 'block') {
                this.cursor.style.left = e.clientX + 'px';
                this.cursor.style.top = e.clientY + 'px';
            }
        });
    }

    highlightElement(element, duration = 1000) {
        const rect = element.getBoundingClientRect();

        this.highlightBox.style.display = 'block';
        this.highlightBox.style.left = (rect.left + window.scrollX) + 'px';
        this.highlightBox.style.top = (rect.top + window.scrollY) + 'px';
        this.highlightBox.style.width = rect.width + 'px';
        this.highlightBox.style.height = rect.height + 'px';

        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => {
                this.highlightBox.style.display = 'none';
            }, duration);
        }
        setTimeout(() => {
            this.highlightBox.style.display = 'none';
        }, duration);
    }
    enableElementPicker(callback) {
        this.elementPickerActive = true;
        this.elementPickerCallback = callback;

        // Add hover listener
        const hoverHandler = (e) => {
            if (!this.elementPickerActive) return;

            e.stopPropagation();
            this.highlightElement(e.target, 0);
        };

        // Add click listener
        const clickHandler = (e) => {
            if (!this.elementPickerActive) return;

            e.preventDefault();
            e.stopPropagation();

            // Disable picker
            this.elementPickerActive = false;
            this.highlightBox.style.display = 'none';

            // Remove listeners
            document.removeEventListener('mouseover', hoverHandler, true);
            document.removeEventListener('click', clickHandler, true);

            // Call callback with picked element
            if (this.elementPickerCallback) {
                this.elementPickerCallback(e.target);
            }
        };

        document.addEventListener('mouseover', hoverHandler, true);
        document.addEventListener('click', clickHandler, true);
    }


    showVariablePrompt(element, onConfirm) {
        const rect = element.getBoundingClientRect();

        // Reset content
        this.variablePrompt.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 0;">
                <span style="color: #4b5563;">Create variable?</span>
                <button id="vandalizer-var-yes" style="background: #3b82f6; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer;">Yes</button>
                <button id="vandalizer-var-no" style="background: transparent; color: #6b7280; border: 1px solid #d1d5db; padding: 3px 8px; border-radius: 4px; cursor: pointer;">No</button>
            </div>
            <div id="vandalizer-var-input-container" style="display: none; margin-top: 8px;">
                <input type="text" id="vandalizer-var-name" placeholder="e.g. student_id" style="width: 100%; border: 1px solid #d1d5db; border-radius: 4px; padding: 4px; box-sizing: border-box; margin-bottom: 4px;">
                <div style="display: flex; justify-content: flex-end; gap: 4px;">
                    <button id="vandalizer-var-save" style="background: #10b981; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer;">Save</button>
                </div>
            </div>
        `;

        this.variablePrompt.style.display = 'block';
        this.variablePrompt.style.top = (rect.bottom + window.scrollY + 5) + 'px';
        this.variablePrompt.style.left = (rect.left + window.scrollX) + 'px';

        const yesBtn = document.getElementById('vandalizer-var-yes');
        const noBtn = document.getElementById('vandalizer-var-no');
        const inputContainer = document.getElementById('vandalizer-var-input-container');
        const input = document.getElementById('vandalizer-var-name');
        const saveBtn = document.getElementById('vandalizer-var-save');

        yesBtn.onclick = () => {
            yesBtn.style.display = 'none';
            noBtn.style.display = 'none';
            this.variablePrompt.querySelector('span').textContent = 'Variable Name:';
            inputContainer.style.display = 'block';
            input.focus();
        };

        noBtn.onclick = () => {
            this.variablePrompt.style.display = 'none';
        };

        saveBtn.onclick = () => {
            const name = input.value.trim();
            if (name && onConfirm) {
                onConfirm(name);
                this.variablePrompt.style.display = 'none';
            }
        };

        // Close on click outside (simple handler)
        setTimeout(() => {
            const closeHandler = (e) => {
                if (!this.variablePrompt.contains(e.target)) {
                    this.variablePrompt.style.display = 'none';
                    document.removeEventListener('click', closeHandler);
                }
            };
            document.addEventListener('click', closeHandler);
        }, 100);
    } // End showVariablePrompt

    showExtractionPrompt(element, onExtract) {
        const rect = element.getBoundingClientRect();

        // Reset content
        this.variablePrompt.innerHTML = `
            <div style="margin-bottom: 8px; font-weight: 600; color: #374151;">Extraction Type</div>
            <div style="display: flex; gap: 8px;">
                <button id="vandalizer-extract-single" style="background: #3b82f6; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;">Single Value</button>
                <button id="vandalizer-extract-list" style="background: white; color: #374151; border: 1px solid #d1d5db; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;">List Example</button>
            </div>
            
            <div id="vandalizer-extract-input-container" style="display: none; margin-top: 8px; border-top: 1px solid #e5e7eb; padding-top: 8px;">
                <label style="display: block; font-size: 11px; margin-bottom: 4px; color: #6b7280;">Variable Name</label>
                <input type="text" id="vandalizer-extract-name" placeholder="e.g. account_balance" style="width: 100%; border: 1px solid #d1d5db; border-radius: 4px; padding: 4px; box-sizing: border-box; margin-bottom: 4px;">
                <div style="display: flex; justify-content: flex-end;">
                    <button id="vandalizer-extract-save" style="background: #10b981; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer;">Save Variable</button>
                </div>
            </div>
        `;

        this.variablePrompt.style.display = 'block'; // Show first to measure

        const modalHeight = this.variablePrompt.offsetHeight;
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;

        // Smart positioning: Flip if not enough space below
        if (spaceBelow < (modalHeight + 100) && spaceAbove > (modalHeight + 50)) {
            // Position above
            this.variablePrompt.style.top = (rect.top + window.scrollY - modalHeight - 10) + 'px';
        } else {
            // Position below (default)
            this.variablePrompt.style.top = (rect.bottom + window.scrollY + 5) + 'px';
        }

        this.variablePrompt.style.left = (rect.left + window.scrollX) + 'px';

        // Ensure prompt stays on screen horizontally
        if (parseInt(this.variablePrompt.style.left) + this.variablePrompt.clientWidth > window.innerWidth) {
            this.variablePrompt.style.left = (window.innerWidth - this.variablePrompt.clientWidth - 10) + 'px';
        }

        const singleBtn = document.getElementById('vandalizer-extract-single');
        const listBtn = document.getElementById('vandalizer-extract-list');
        const inputContainer = document.getElementById('vandalizer-extract-input-container');
        const input = document.getElementById('vandalizer-extract-name');
        const saveBtn = document.getElementById('vandalizer-extract-save');

        singleBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            inputContainer.style.display = 'block';

            // Recalculate position if we flipped above, because height changed!
            const newHeight = this.variablePrompt.offsetHeight;
            // Must match the original positioning logic with BOTH conditions
            const isAbove = spaceBelow < (modalHeight + 100) && spaceAbove > (modalHeight + 50);

            if (isAbove) {
                // Adjust top to account for grew height
                this.variablePrompt.style.top = (rect.top + window.scrollY - newHeight - 10) + 'px';
            }

            singleBtn.style.background = '#2563eb';
            listBtn.style.background = 'white';
            input.focus({ preventScroll: true });
        };

        listBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.variablePrompt.style.display = 'none';
            if (onExtract) onExtract({ type: 'list' });
        };

        saveBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            const name = input.value.trim();
            if (name && onExtract) {
                onExtract({ type: 'single', name: name });
                this.variablePrompt.style.display = 'none';
            }
        };

        // Close on click outside
        setTimeout(() => {
            const closeHandler = (e) => {
                if (!this.variablePrompt.contains(e.target) && !element.contains(e.target)) {
                    this.variablePrompt.style.display = 'none';
                    document.removeEventListener('click', closeHandler);
                }
            };
            document.addEventListener('click', closeHandler);
        }, 100);
    }

    addHighlight(element, color = 'rgb(34, 197, 94)') {
        const rect = element.getBoundingClientRect();
        const box = document.createElement('div');

        box.style.cssText = `
            position: absolute;
            border: 2px solid ${color};
            background: ${color.replace('rgb', 'rgba').replace(')', ', 0.1)')};
            pointer-events: none;
            z-index: 999998;
            left: ${rect.left + window.scrollX}px;
            top: ${rect.top + window.scrollY}px;
            width: ${rect.width}px;
            height: ${rect.height}px;
            transition: all 0.2s ease;
        `;

        document.body.appendChild(box);
        this.highlights.push(box);
        return box;
    }

    clearHighlights() {
        this.highlights.forEach(el => el.remove());
        this.highlights = [];
        if (this.highlightBox) this.highlightBox.style.display = 'none';
        if (this.variablePrompt) this.variablePrompt.style.display = 'none';
    }

    showAutocomplete(element, variables) {
        // Remove existing
        const existing = document.getElementById('vandalizer-autocomplete');
        if (existing) existing.remove();

        const rect = element.getBoundingClientRect();
        const container = document.createElement('div');
        container.id = 'vandalizer-autocomplete';
        container.style.cssText = `
            position: absolute;
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            z-index: 2147483647;
            font-family: sans-serif;
            font-size: 13px;
            min-width: 150px;
            max-height: 200px;
            overflow-y: auto;
            top: ${rect.bottom + window.scrollY + 5}px;
            left: ${rect.left + window.scrollX}px;
        `;

        variables.forEach(v => {
            const item = document.createElement('div');
            item.textContent = v;
            item.style.cssText = `
                padding: 8px 12px;
                cursor: pointer;
                color: #374151;
            `;
            item.onmouseover = () => item.style.background = '#f3f4f6';
            item.onmouseout = () => item.style.background = 'transparent';
            item.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation(); // Stop bubbling

                // Insert variable
                const val = `{{${v}}}`;
                const start = element.selectionStart || element.value.length;
                const end = element.selectionEnd || element.value.length;
                element.value = element.value.substring(0, start) + val + element.value.substring(end);

                container.remove();
            };
            container.appendChild(item);
        });

        document.body.appendChild(container);

        // Close on outside click
        setTimeout(() => {
            const closeHandler = (e) => {
                if (!container.contains(e.target) && e.target !== element) {
                    container.remove();
                    document.removeEventListener('click', closeHandler);
                }
            };
            document.addEventListener('click', closeHandler);
        }, 100);
    }
}
