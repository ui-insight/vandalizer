class TargetPicker {
    constructor() {
        this.isActive = false;
        this.overlay = null;
        this.selectedElement = null;
        this.onComplete = null;
    }

    start(callback) {
        this.isActive = true;
        this.onComplete = callback;

        // Create overlay
        this.overlay = document.createElement('div');
        this.overlay.id = 'vandalizer-target-picker-overlay';
        this.overlay.innerHTML = `
            <div class="picker-banner">
                Click on the element you want to select
                <button id="picker-cancel">Cancel</button>
            </div>
        `;
        document.body.appendChild(this.overlay);

        // Add event listeners
        document.addEventListener('mouseover', this.handleHover.bind(this), true);
        document.addEventListener('click', this.handleClick.bind(this), true);
        document.getElementById('picker-cancel').addEventListener('click', this.cancel.bind(this));
    }

    handleHover(event) {
        if (!this.isActive) return;
        event.stopPropagation();

        // Highlight hovered element
        this.removeHighlight();
        event.target.classList.add('vandalizer-picker-highlight');
    }

    async handleClick(event) {
        if (!this.isActive) return;
        event.preventDefault();
        event.stopPropagation();

        this.selectedElement = event.target;

        // Generate locator strategies for this element
        const strategies = await this.generateStrategies(this.selectedElement);

        // Show preview and confidence
        this.showPreview(strategies);

        // User confirms logic is handled in confirmation UI
    }

    async generateStrategies(element) {
        const strategies = [];
        let priority = 1;

        // 1. data-testid
        if (element.dataset.testid) {
            strategies.push({
                type: 'data-testid',
                value: element.dataset.testid,
                priority: priority++,
                description: `data-testid="${element.dataset.testid}"`
            });
        }

        // 2. ID
        if (element.id) {
            strategies.push({
                type: 'id',
                value: element.id,
                priority: priority++,
                description: `id="${element.id}"`
            });
        }

        // 3. aria-label
        if (element.getAttribute('aria-label')) {
            strategies.push({
                type: 'aria-label',
                value: element.getAttribute('aria-label'),
                priority: priority++,
                description: `aria-label="${element.getAttribute('aria-label')}"`
            });
        }

        // 4. Role + accessible name
        const role = element.getAttribute('role') || this.getImplicitRole(element);
        if (role) {
            const name = element.getAttribute('aria-label') || element.innerText.trim().slice(0, 30);
            strategies.push({
                type: 'role',
                role: role,
                name: name,
                priority: priority++,
                description: `${role} "${name}"`
            });
        }

        // 5. Text match (for buttons, links)
        if (['BUTTON', 'A', 'SPAN'].includes(element.tagName) && element.innerText.trim()) {
            strategies.push({
                type: 'text',
                value: element.innerText.trim(),
                match: 'exact',
                priority: priority++,
                description: `Text: "${element.innerText.trim().slice(0, 30)}..."`
            });
        }

        // 6. Name attribute (for inputs)
        if (element.name) {
            strategies.push({
                type: 'name',
                value: element.name,
                priority: priority++,
                description: `name="${element.name}"`
            });
        }

        // 7. Relative to label (for inputs)
        const label = this.findLabelForInput(element);
        if (label) {
            strategies.push({
                type: 'relative',
                anchor: { type: 'text', value: label.innerText.trim() },
                relation: 'next_sibling',
                priority: priority++,
                description: `Input next to label "${label.innerText.trim()}"`
            });
        }

        // 8. CSS selector (last resort)
        const cssSelector = this.generateCSSSelector(element);
        strategies.push({
            type: 'css',
            value: cssSelector,
            priority: priority++,
            description: `CSS: ${cssSelector}`
        });

        return strategies;
    }

    getImplicitRole(element) {
        const roleMap = {
            'BUTTON': 'button',
            'A': 'link',
            'INPUT': element.type === 'checkbox' ? 'checkbox' : 'textbox',
            'SELECT': 'combobox',
            'TEXTAREA': 'textbox',
            'H1': 'heading',
            'H2': 'heading',
            'H3': 'heading'
        };
        return roleMap[element.tagName];
    }

    findLabelForInput(element) {
        // Check for label with for attribute
        if (element.id) {
            const label = document.querySelector(`label[for="${element.id}"]`);
            if (label) return label;
        }

        // Check for wrapping label
        let parent = element.parentElement;
        while (parent && parent.tagName !== 'LABEL') {
            parent = parent.parentElement;
        }
        return parent;
    }

    generateCSSSelector(element) {
        if (element.id) return `#${element.id}`;
        if (element.className) {
            const classes = element.className.split(' ').filter(c => c.trim() && !c.includes('vandalizer'));
            if (classes.length > 0) {
                return `${element.tagName.toLowerCase()}.${classes.join('.')}`;
            }
        }

        // Fallback: nth-child
        if (!element.parentElement) return element.tagName.toLowerCase();

        const parent = element.parentElement;
        const index = Array.from(parent.children).indexOf(element);
        return `${this.generateCSSSelector(parent)} > ${element.tagName.toLowerCase()}:nth-child(${index + 1})`;
    }

    async showPreview(strategies) {
        // Test each strategy and show results
        const preview = document.createElement('div');
        preview.className = 'picker-preview';
        preview.innerHTML = `
            <h3>Generated Locator Strategies (in order of preference):</h3>
            <ul>
                ${strategies.map((s, i) => `
                    <li>
                        <strong>${i + 1}.</strong> ${s.description}
                        <span class="confidence">${this.getConfidence(s)}% confidence</span>
                    </li>
                `).join('')}
            </ul>
            <div class="picker-actions">
                <button id="confirm-target">Confirm</button>
                <button id="retry-target">Pick Different Element</button>
            </div>
        `;

        this.overlay.appendChild(preview);

        // Bind confirmation buttons
        document.getElementById('confirm-target').onclick = () => {
            this.complete(strategies);
        };

        document.getElementById('retry-target').onclick = () => {
            preview.remove();
            this.selectedElement = null;
            // Picking mode implicit via listeners still being active
        };
    }

    getConfidence(strategy) {
        const scores = {
            'data-testid': 95,
            'id': 90,
            'aria-label': 85,
            'role': 80,
            'name': 75,
            'text': 70,
            'relative': 65,
            'css': 50
        };
        return scores[strategy.type] || 50;
    }

    complete(strategies) {
        this.isActive = false;
        this.cleanup();

        if (this.onComplete) {
            this.onComplete(strategies);
        }
    }

    cancel() {
        this.isActive = false;
        this.cleanup();
    }

    cleanup() {
        document.removeEventListener('mouseover', this.handleHover.bind(this), true);
        document.removeEventListener('click', this.handleClick.bind(this), true);
        this.removeHighlight();
        if (this.overlay) {
            this.overlay.remove();
        }
    }

    removeHighlight() {
        document.querySelectorAll('.vandalizer-picker-highlight').forEach(el => {
            el.classList.remove('vandalizer-picker-highlight');
        });
    }
}

// Export for use in content script
window.VandalizerTargetPicker = TargetPicker;
