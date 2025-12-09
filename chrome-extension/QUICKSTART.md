# Quick Start: Socket.IO Integration

## Simplest Solution - Use CDN in Manifest

The easiest way to get Socket.IO working is to load it from a CDN script.

### Step 1: Update manifest.json

Keep it as a module and add the Socket.IO library as a web accessible resource:

```json
"background": {
  "service_worker": "background/service-worker.js",
  "type": "module"
},
"web_accessible_resources": [
  {
    "resources": ["assets/*", "lib/*"],
    "matches": ["<all_urls>"]
  }
]
```

### Step 2: Replace service-worker.js content

The issue with the current setup is that ES6 modules in service workers can't use `importScripts()`.

**OPTION A: Use Non-Module Service Worker (RECOMMENDED)**

1. Remove `"type": "module"` from manifest.json (already done)
2. Replace the imports with `importScripts()`:

```javascript
// Load Socket.IO library
importScripts('../lib/socket.io.min.js');

// Load other scripts (convert from ES6 modules to plain scripts)
importScripts('./session-manager.js');
importScripts('./command-handler.js');

// Now the rest of your code works the same...
```

**OPTION B: Keep ES6 Modules (requires bundler)**

Use a bundler like Rollup or Webpack to bundle Socket.IO with your code.

## Recommended Approach: Non-Module

Since you already have the socket.io.min.js downloaded, here's what to do:

1. ✅ Manifest updated (type: module removed)
2. ✅ Socket.IO library downloaded to lib/socket.io.min.js
3. **TODO**: Convert session-manager.js and command-handler.js from ES6 modules to plain scripts
4. **TODO**: Update service-worker.js to use importScripts

### Quick Fix (Copy & Replace)

I can create a complete working version if you want to just replace the whole background directory. Would you like me to:

A) Create a complete non-module version (ready to use)
B) Show you how to convert the existing ES6 modules
C) Set up a bundler to keep ES6 syntax

**For quickest results, choose A.**

## Testing

Once updated:

1. Open `chrome://extensions`
2. Click **Reload** on the extension
3. Click **Inspect views: service worker**
4. You should see in console:
   ```
   [BrowserAutomation] Connecting to http://localhost:5003/browser_automation...
   [BrowserAutomation] Socket connected, waiting for authentication...
   [BrowserAutomation] ✅ Authenticated as: your_user_id
   ```

## Troubleshooting

**"io is not defined"**
- Socket.IO didn't load. Check that `importScripts()` is at the very top of the file.
- Check browser console for CSP errors.

**"Unexpected token 'import'"**
- You still have ES6 imports in a non-module service worker.
- Either remove `import` statements or add back `"type": "module"` to manifest.

**Connection refused**
- Backend not running or wrong URL.
- Check that Flask server is running with `python run.py`.
