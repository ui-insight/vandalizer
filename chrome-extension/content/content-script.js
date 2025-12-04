// Main content script - coordinates between background and page
class BrowserAutomationContent {
    constructor() {
        this.overlay = new OverlayManager();
        this.domActions = new DOMActions();
        this.extractor = new DataExtractor();

        this.setupListeners();
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

    async fillForm(data) {
        const { field_mappings, options } = data;
        const results = [];

        for (const mapping of field_mappings) {
            const { locator, value } = mapping;

            try {
                const element = this.domActions.findElement(locator);

                if (!element) {
                    results.push({
                        locator,
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
                    value,
                    options?.typing_delay_ms || 0
                );

                results.push({ locator, success: true });
            } catch (error) {
                results.push({
                    locator,
                    success: false,
                    error: error.message
                });
            }
        }

        return { field_results: results };
    }

    async clickElement(data) {
        const { locator, click_type } = data;

        const element = this.domActions.findElement(locator);

        if (!element) {
            throw new Error('Element not found');
        }

        // Highlight and click
        this.overlay.highlightElement(element);
        await this.domActions.clickElement(element, click_type);

        return { success: true };
    }

    async extractData(data) {
        const { extraction_spec } = data;

        return this.extractor.extract(extraction_spec);
    }

    async scrollPage(data) {
        const { direction, distance, target_locator, smooth } = data;

        if (target_locator) {
            const element = this.domActions.findElement(target_locator);
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
                const element = this.domActions.findElement({
                    strategy: 'css',
                    value: condition_value
                });
                return { met: !!element };

            case 'element_visible':
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
