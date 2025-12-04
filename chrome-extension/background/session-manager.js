export class SessionManager {
    constructor() {
        this.sessions = new Map(); // sessionId -> { id, tabId, allowedDomains, state }
        this.tabToSession = new Map(); // tabId -> sessionId
    }

    createSession(sessionId, tabId, allowedDomains = []) {
        const session = {
            id: sessionId,
            tabId,
            allowedDomains,
            state: 'READY_NO_LOGIN',
            createdAt: Date.now()
        };

        this.sessions.set(sessionId, session);
        this.tabToSession.set(tabId, sessionId);

        return session;
    }

    getSession(sessionId) {
        return this.sessions.get(sessionId);
    }

    getSessionByTabId(tabId) {
        const sessionId = this.tabToSession.get(tabId);
        return sessionId ? this.sessions.get(sessionId) : null;
    }

    removeSession(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            this.tabToSession.delete(session.tabId);
            this.sessions.delete(sessionId);
        }
    }

    updateState(sessionId, newState) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.state = newState;
        }
    }

    isDomainAllowed(sessionId, hostname) {
        const session = this.sessions.get(sessionId);
        if (!session || session.allowedDomains.length === 0) {
            return true; // No restrictions
        }

        return session.allowedDomains.some(allowed => {
            // Support wildcards like *.example.com
            const pattern = allowed.replace(/\*/g, '.*');
            const regex = new RegExp(`^${pattern}$`);
            return regex.test(hostname);
        });
    }
}
