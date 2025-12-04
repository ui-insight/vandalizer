class DOMActions {
    findElement(locator) {
        const { strategy, value } = locator;

        switch (strategy) {
            case 'css':
                return document.querySelector(value);

            case 'xpath':
                const result = document.evaluate(
                    value,
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                return result.singleNodeValue;

            case 'id':
                return document.getElementById(value);

            case 'name':
                return document.querySelector(`[name="${value}"]`);

            case 'semantic':
                // Try to find by label text, placeholder, aria-label, etc.
                return this.findBySemantic(value);

            default:
                throw new Error(`Unknown locator strategy: ${strategy}`);
        }
    }

    findBySemantic(description) {
        // Try various semantic selectors
        const selectors = [
            `[aria-label*="${description}" i]`,
            `[placeholder*="${description}" i]`,
            `label:has-text("${description}") input`,
            `button:has-text("${description}")`,
            `a:has-text("${description}")`
        ];

        for (const selector of selectors) {
            try {
                const element = document.querySelector(selector);
                if (element) return element;
            } catch (e) {
                // Some selectors might not be valid
            }
        }

        // Fallback: search by text content
        const xpath = `//*[contains(text(), "${description}")]`;
        const result = document.evaluate(
            xpath,
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null
        );

        return result.singleNodeValue;
    }

    async typeIntoElement(element, text, delayMs = 0) {
        // Focus element
        element.focus();

        // Type character by character for human-like behavior
        if (delayMs > 0) {
            for (const char of text) {
                element.value += char;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                await new Promise(resolve => setTimeout(resolve, delayMs));
            }
        } else {
            element.value = text;
            element.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Trigger change event
        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    async clickElement(element, clickType = 'single') {
        // Scroll into view
        element.scrollIntoView({ block: 'center' });

        // Wait a bit for scroll
        await new Promise(resolve => setTimeout(resolve, 100));

        switch (clickType) {
            case 'single':
                element.click();
                break;

            case 'double':
                element.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
                break;

            case 'context':
                element.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }));
                break;
        }
    }

    isElementVisible(element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);

        return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            style.opacity !== '0'
        );
    }

    generateSelector(element) {
        // Generate robust CSS selector
        const id = element.id;
        if (id) {
            return {
                strategy: 'css',
                value: `#${id}`,
                semantic: this.getSemanticInfo(element)
            };
        }

        const name = element.getAttribute('name');
        if (name) {
            return {
                strategy: 'css',
                value: `[name="${name}"]`,
                semantic: this.getSemanticInfo(element)
            };
        }

        // Build selector from tag + classes
        let selector = element.tagName.toLowerCase();
        const classes = Array.from(element.classList).filter(c => !c.startsWith('overlay-'));
        if (classes.length > 0) {
            selector += '.' + classes.join('.');
        }

        // Add nth-child if needed for uniqueness
        const siblings = Array.from(element.parentElement?.children || [])
            .filter(e => e.tagName === element.tagName);

        if (siblings.length > 1) {
            const index = siblings.indexOf(element) + 1;
            selector += `:nth-child(${index})`;
        }

        return {
            strategy: 'css',
            value: selector,
            semantic: this.getSemanticInfo(element)
        };
    }

    getSemanticInfo(element) {
        return {
            label: element.getAttribute('aria-label'),
            placeholder: element.getAttribute('placeholder'),
            text: element.innerText?.substring(0, 50),
            type: element.getAttribute('type'),
            role: element.getAttribute('role')
        };
    }
}
