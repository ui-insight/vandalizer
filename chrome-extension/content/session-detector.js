/**
 * SessionDetector - Detects when user is logged out
 * Monitors for SSO timeouts, Duo prompts, login redirects
 */

class SessionDetector {
    constructor() {
        this.isMonitoring = false;
        this.checkInterval = null;
        this.lastState = 'authenticated';
        this.onSessionExpired = null;
        this.onSessionRestored = null;
    }

    /**
     * Start monitoring for session expiration
     * @param {Function} onExpired - Callback when session expires
     * @param {Function} onRestored - Callback when session is restored
     */
    start(onExpired, onRestored) {
        if (this.isMonitoring) {
            console.log('[SessionDetector] Already monitoring');
            return;
        }

        this.onSessionExpired = onExpired;
        this.onSessionRestored = onRestored;
        this.isMonitoring = true;

        // Check immediately
        this.checkSessionState();

        // Check every 2 seconds
        this.checkInterval = setInterval(() => {
            this.checkSessionState();
        }, 2000);

        console.log('[SessionDetector] Started monitoring for session expiration');
    }

    /**
     * Stop monitoring
     */
    stop() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
        }
        this.isMonitoring = false;
        console.log('[SessionDetector] Stopped monitoring');
    }

    /**
     * Check current session state
     */
    checkSessionState() {
        const currentState = this.detectSessionState();

        // State changed
        if (currentState !== this.lastState) {
            console.log(`[SessionDetector] State changed: ${this.lastState} → ${currentState}`);

            if (currentState === 'logged_out' && this.lastState === 'authenticated') {
                // Session expired
                this.handleSessionExpired();
            } else if (currentState === 'authenticated' && this.lastState === 'logged_out') {
                // Session restored
                this.handleSessionRestored();
            }

            this.lastState = currentState;
        }
    }

    /**
     * Detect current session state
     * @returns {string} 'authenticated' | 'logged_out'
     */
    detectSessionState() {
        // Check URL patterns
        const url = window.location.href.toLowerCase();
        const urlPatterns = [
            '/login',
            '/signin',
            '/sign-in',
            '/sso',
            '/auth',
            '/authenticate',
            '/saml',
            '/oauth',
            '/duo',
            'cas.login'  // Common for university systems
        ];

        for (const pattern of urlPatterns) {
            if (url.includes(pattern)) {
                console.log(`[SessionDetector] Detected logout URL pattern: ${pattern}`);
                return 'logged_out';
            }
        }

        // Check page title
        const title = document.title.toLowerCase();
        const titlePatterns = [
            'sign in',
            'log in',
            'login',
            'authentication',
            'duo security',
            'sso',
            'single sign-on',
            'session expired',
            'session timeout'
        ];

        for (const pattern of titlePatterns) {
            if (title.includes(pattern)) {
                console.log(`[SessionDetector] Detected logout title pattern: ${pattern}`);
                return 'logged_out';
            }
        }

        // Check for common login form elements
        const loginIndicators = [
            'input[type="password"][name*="password"]',
            'input[name="username"]',
            'input[name="login"]',
            'button[type="submit"][value*="sign in"]',
            'button[type="submit"][value*="log in"]',
            'form[action*="login"]',
            'form[action*="signin"]',
            'form[action*="auth"]',
            'div[class*="login-form"]',
            'div[id*="login-form"]',
            // Duo-specific
            'iframe[id*="duo"]',
            'div[id*="duo"]'
        ];

        for (const selector of loginIndicators) {
            const element = document.querySelector(selector);
            if (element && this.isVisible(element)) {
                console.log(`[SessionDetector] Detected login element: ${selector}`);
                return 'logged_out';
            }
        }

        // Check for session expired messages
        const bodyText = document.body?.textContent?.toLowerCase() || '';
        const expiredPhrases = [
            'session expired',
            'session has expired',
            'session timeout',
            'logged out',
            'please log in',
            'please sign in',
            'authentication required',
            'your session has timed out'
        ];

        for (const phrase of expiredPhrases) {
            if (bodyText.includes(phrase)) {
                console.log(`[SessionDetector] Detected expired phrase: ${phrase}`);
                return 'logged_out';
            }
        }

        // Default: assume authenticated
        return 'authenticated';
    }

    /**
     * Check if element is visible
     */
    isVisible(element) {
        if (!element) return false;

        const style = window.getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
        }

        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    /**
     * Handle session expiration
     */
    handleSessionExpired() {
        console.log('[SessionDetector] 🚨 SESSION EXPIRED - Triggering callback');

        if (this.onSessionExpired) {
            this.onSessionExpired({
                url: window.location.href,
                title: document.title,
                timestamp: new Date().toISOString()
            });
        }
    }

    /**
     * Handle session restoration
     */
    handleSessionRestored() {
        console.log('[SessionDetector] ✅ SESSION RESTORED - Triggering callback');

        if (this.onSessionRestored) {
            this.onSessionRestored({
                url: window.location.href,
                title: document.title,
                timestamp: new Date().toISOString()
            });
        }
    }

    /**
     * Manually check if currently logged out
     * @returns {boolean}
     */
    isLoggedOut() {
        return this.detectSessionState() === 'logged_out';
    }
}

// Export for use in content script
window.VandalizerSessionDetector = SessionDetector;
