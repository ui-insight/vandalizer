class OverlayManager {
    constructor() {
        this.cursor = null;
        this.highlightBox = null;
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
}
