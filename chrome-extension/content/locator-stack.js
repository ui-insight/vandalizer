class LocatorStack {
    constructor(strategies) {
        this.strategies = strategies.sort((a, b) => a.priority - b.priority);
    }

    async findElement(timeoutMs = 5000) {
        const startTime = Date.now();
        const results = [];

        // Poll until timeout
        while (Date.now() - startTime < timeoutMs) {
            for (const strategy of this.strategies) {
                try {
                    const element = await this.tryStrategy(strategy);
                    if (element && this.isVisible(element)) {
                        results.push({
                            strategy: strategy,
                            element: element,
                            success: true,
                            attempt: results.length + 1
                        });
                        return { element, usedStrategy: strategy, allAttempts: results };
                    }
                } catch (error) {
                    // Ignore errors during polling
                }
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, 200));
        }

        // Final attempt to record failure reasons
        for (const strategy of this.strategies) {
            try {
                const element = await this.tryStrategy(strategy);
                results.push({
                    strategy: strategy,
                    success: false,
                    reason: element ? 'not_visible' : 'not_found'
                });
            } catch (error) {
                results.push({
                    strategy: strategy,
                    success: false,
                    reason: 'error',
                    error: error.message
                });
            }
        }

        throw new LocatorStackFailure('All strategies failed after timeout', results);
    }

    async tryStrategy(strategy) {
        switch (strategy.type) {
            case 'data-testid':
                return document.querySelector(`[data-testid="${strategy.value}"]`);
            case 'aria-label':
                return document.querySelector(`[aria-label="${strategy.value}"]`);
            case 'role':
                return this.findByRole(strategy.role, strategy.name);
            case 'text':
                return this.findByText(strategy.value, strategy.match);
            case 'css':
                return document.querySelector(strategy.value);
            case 'xpath':
                return document.evaluate(strategy.value, document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            case 'relative':
                return this.findRelative(strategy);
            default:
                throw new Error(`Unknown strategy type: ${strategy.type}`);
        }
    }

    findByRole(role, accessibleName) {
        const candidates = document.querySelectorAll(`[role="${role}"]`);
        if (!accessibleName) return candidates[0];

        for (const el of candidates) {
            const name = el.getAttribute('aria-label') || el.innerText.trim();
            if (name === accessibleName || name.includes(accessibleName)) {
                return el;
            }
        }
        return null;
    }

    findByText(text, matchType = 'exact') {
        const xpath = matchType === 'exact'
            ? `//*[text()='${text}']`
            : `//*[contains(text(),'${text}')]`;
        return document.evaluate(xpath, document, null,
            XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    }

    findRelative(strategy) {
        // Example: find input next to label
        const anchor = this.tryStrategy(strategy.anchor);
        if (!anchor) return null;

        switch (strategy.relation) {
            case 'next_sibling':
                return anchor.nextElementSibling;
            case 'child':
                return anchor.querySelector(strategy.selector);
            case 'parent':
                return anchor.closest(strategy.selector);
            default:
                return null;
        }
    }

    isVisible(element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 &&
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            style.opacity !== '0';
    }
}

class LocatorStackFailure extends Error {
    constructor(message, results) {
        super(message);
        this.name = 'LocatorStackFailure';
        this.results = results;
    }
}

// Export for use
window.LocatorStack = LocatorStack;
