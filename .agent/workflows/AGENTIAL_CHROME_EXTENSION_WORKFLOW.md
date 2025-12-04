---
description: Complete workflow for building Chrome extensions with agentic AI assistance
---

# Agential Chrome Extension Development Workflow

This workflow provides a comprehensive guide for building Chrome extensions using AI assistance, from initial planning through deployment.

## Phase 1: Planning & Architecture

### 1.1 Define Extension Requirements
- Identify the core functionality and user problem being solved
- List all required permissions (tabs, storage, activeTab, etc.)
- Determine if background scripts, content scripts, or both are needed
- Identify which websites/URLs the extension will interact with
- Define the UI components needed (popup, options page, side panel, etc.)

### 1.2 Review Chrome Extension Documentation
- Check the latest Manifest V3 requirements at https://developer.chrome.com/docs/extensions/mv3/
- Review API documentation for required features
- Understand permission requirements and best practices
- Note any deprecated APIs if migrating from Manifest V2

### 1.3 Create Implementation Plan
- Document the extension architecture in `implementation_plan.md`
- Define the manifest.json structure
- Plan the file structure (popup, background, content scripts, etc.)
- Identify third-party libraries or dependencies needed
- Plan the communication flow between components

## Phase 2: Project Setup

### 2.1 Create Project Structure
```
extension-name/
├── manifest.json
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
├── popup/
│   ├── popup.html
│   ├── popup.css
│   └── popup.js
├── background/
│   └── background.js
├── content/
│   ├── content.js
│   └── content.css
├── options/
│   ├── options.html
│   ├── options.css
│   └── options.js
└── utils/
    └── storage.js
```

### 2.2 Create manifest.json
- Set manifest_version to 3
- Define name, version, and description
- Specify required permissions
- Configure background service worker
- Define content scripts and their match patterns
- Set up browser action/page action
- Include web_accessible_resources if needed

Example:
```json
{
  "manifest_version": 3,
  "name": "Extension Name",
  "version": "1.0.0",
  "description": "Extension description",
  "permissions": ["storage", "activeTab"],
  "host_permissions": ["https://*/*"],
  "background": {
    "service_worker": "background/background.js"
  },
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content/content.js"],
      "css": ["content/content.css"]
    }
  ]
}
```

### 2.3 Generate Icons
// turbo
- Use the `generate_image` tool to create extension icons
- Generate at minimum: 16x16, 48x48, and 128x128 pixel versions
- Ensure icons are clear and recognizable at all sizes
- Save icons in the `icons/` directory

## Phase 3: Core Implementation

### 3.1 Implement Background Service Worker
- Set up event listeners (chrome.runtime.onInstalled, etc.)
- Implement message passing handlers
- Set up alarms or periodic tasks if needed
- Handle extension lifecycle events
- Implement core business logic that runs independently

### 3.2 Implement Content Scripts
- Write DOM manipulation code
- Set up message passing with background script
- Implement page-specific functionality
- Handle dynamic content (MutationObserver if needed)
- Ensure scripts don't conflict with page scripts

### 3.3 Implement Popup UI
- Create HTML structure with semantic markup
- Style with modern CSS (use design best practices)
- Implement interactive JavaScript
- Set up communication with background script
- Handle user input and display data from storage

### 3.4 Implement Storage Layer
- Use chrome.storage.sync for user preferences
- Use chrome.storage.local for larger data
- Implement storage utility functions (get, set, clear)
- Handle storage quota limits
- Implement data migration if needed

### 3.5 Implement Message Passing
- Set up chrome.runtime.sendMessage for one-time requests
- Use chrome.runtime.onMessage listeners
- Implement chrome.tabs.sendMessage for tab-specific messages
- Handle message responses with promises
- Implement error handling for failed messages

## Phase 4: Advanced Features

### 4.1 Options Page (if needed)
- Create options.html with settings UI
- Implement options.js to save/load preferences
- Style consistently with popup
- Add options_page or options_ui to manifest.json

### 4.2 Context Menus (if needed)
- Use chrome.contextMenus API
- Create menu items in background script
- Handle menu click events
- Add "contextMenus" permission to manifest

### 4.3 Notifications (if needed)
- Use chrome.notifications API
- Create rich notifications with actions
- Handle notification click events
- Add "notifications" permission to manifest

### 4.4 Web Requests Interception (if needed)
- Use chrome.webRequest or chrome.declarativeNetRequest
- Define rules for blocking/modifying requests
- Add appropriate permissions and host_permissions
- Test thoroughly to avoid breaking websites

## Phase 5: Testing & Debugging

### 5.1 Load Extension Locally
// turbo
- Navigate to `chrome://extensions/`
- Enable "Developer mode"
- Click "Load unpacked"
- Select the extension directory
- Note the extension ID for testing

### 5.2 Test Core Functionality
- Test popup UI interactions
- Verify content script injection on target pages
- Test background script event handlers
- Verify message passing between components
- Test storage operations (save, retrieve, clear)

### 5.3 Debug Issues
- Use Chrome DevTools for popup (right-click popup → Inspect)
- Use DevTools for background script (Extensions page → Inspect views)
- Use DevTools for content scripts (regular page DevTools)
- Check console for errors in all contexts
- Use chrome.runtime.lastError for API errors

### 5.4 Test Edge Cases
- Test with no internet connection (if applicable)
- Test with empty storage
- Test permission denials
- Test on different websites
- Test rapid user interactions
- Test with extension disabled/re-enabled

### 5.5 Performance Testing
- Check memory usage in Task Manager
- Verify no memory leaks
- Ensure content scripts don't slow page load
- Optimize background script to avoid excessive CPU usage

## Phase 6: Polish & Optimization

### 6.1 Code Quality
- Remove console.log statements (or use conditional logging)
- Add error handling for all async operations
- Validate user input
- Add comments for complex logic
- Follow consistent code style

### 6.2 UI/UX Polish
- Ensure responsive design for popup
- Add loading states for async operations
- Implement error messages for users
- Add helpful tooltips or instructions
- Ensure accessibility (keyboard navigation, ARIA labels)

### 6.3 Security Review
- Validate all external inputs
- Use Content Security Policy
- Avoid eval() and inline scripts
- Sanitize data before inserting into DOM
- Review all permissions (request minimum necessary)

### 6.4 Optimize Performance
- Minimize content script size
- Lazy load non-critical code
- Debounce/throttle event handlers
- Use efficient DOM queries
- Minimize storage operations

## Phase 7: Documentation

### 7.1 Create README.md
- Describe extension purpose and features
- Include installation instructions
- Document any configuration needed
- Add screenshots or demo GIFs
- Include troubleshooting section

### 7.2 Add Code Comments
- Document complex algorithms
- Explain non-obvious design decisions
- Add JSDoc comments for functions
- Document message passing protocols

### 7.3 Create User Guide (if complex)
- Write step-by-step usage instructions
- Include screenshots of UI
- Document all features
- Add FAQ section

## Phase 8: Preparation for Distribution

### 8.1 Create Store Assets
- Write compelling description (132 characters for short, detailed for long)
- Create promotional images (1400x560 marquee, 440x280 small tile)
- Take 1280x800 or 640x400 screenshots
- Create a privacy policy if collecting data
- Prepare category and tags

### 8.2 Final Testing
- Test on fresh Chrome profile
- Test all user flows end-to-end
- Verify all links work
- Check for typos in UI text
- Test on different screen sizes

### 8.3 Version & Changelog
- Update version in manifest.json
- Create CHANGELOG.md with version history
- Document all features in this release
- Note any breaking changes

### 8.4 Package Extension
// turbo
- Create a ZIP file of the extension directory
- Exclude development files (.git, node_modules, etc.)
- Verify ZIP contains all necessary files
- Test the ZIP by loading it as unpacked

Command to create ZIP:
```bash
zip -r extension-name.zip . -x "*.git*" "node_modules/*" "*.DS_Store"
```

## Phase 9: Publishing (Chrome Web Store)

### 9.1 Create Developer Account
- Go to https://chrome.google.com/webstore/devconsole
- Pay one-time $5 developer registration fee
- Complete account setup

### 9.2 Submit Extension
- Click "New Item" in developer dashboard
- Upload ZIP file
- Fill in store listing details
- Upload promotional images and screenshots
- Select category and language
- Set pricing (free or paid)

### 9.3 Privacy & Compliance
- Complete privacy practices disclosure
- Justify all permissions requested
- Provide privacy policy URL if collecting data
- Complete single purpose description
- Ensure compliance with Chrome Web Store policies

### 9.4 Submit for Review
- Review all information for accuracy
- Submit for review
- Monitor email for review status
- Address any rejection reasons promptly

## Phase 10: Post-Launch

### 10.1 Monitor Reviews & Feedback
- Respond to user reviews
- Track common issues or feature requests
- Monitor crash reports (if using error tracking)

### 10.2 Plan Updates
- Prioritize bug fixes
- Plan feature additions based on feedback
- Keep up with Chrome API changes
- Test on Chrome Beta for upcoming changes

### 10.3 Update Extension
- Increment version number
- Update CHANGELOG.md
- Test thoroughly
- Submit update to Chrome Web Store
- Announce major updates to users

## Best Practices & Tips

### Communication Between Components
```javascript
// From content script to background
chrome.runtime.sendMessage({action: "getData"}, (response) => {
  console.log(response);
});

// In background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getData") {
    // Async operation
    getData().then(data => sendResponse({data}));
    return true; // Keep channel open for async response
  }
});
```

### Storage Best Practices
```javascript
// Save data
await chrome.storage.sync.set({key: value});

// Get data
const result = await chrome.storage.sync.get(['key']);
console.log(result.key);

// Listen for changes
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (changes.key) {
    console.log('Key changed:', changes.key.newValue);
  }
});
```

### Content Script Injection Timing
- Use "run_at": "document_idle" (default) for most cases
- Use "document_start" only if you need to run before page loads
- Use "document_end" for DOM-ready but before images load

### Permissions Philosophy
- Request minimum permissions needed
- Use optional_permissions for features users can enable
- Explain why permissions are needed in description
- Use activeTab instead of tabs when possible

### Common Pitfalls to Avoid
- Don't use Manifest V2 (deprecated)
- Don't use inline scripts (CSP violation)
- Don't make synchronous XMLHttpRequest calls
- Don't assume content scripts run immediately
- Don't store sensitive data unencrypted
- Don't exceed storage quotas
- Don't make excessive API calls

### Debugging Tips
- Use `chrome.runtime.lastError` after every chrome API call
- Check background script console separately from popup
- Use `debugger;` statements for breakpoints
- Test in incognito mode to verify permissions
- Use Chrome's Extension DevTools for performance profiling

## Resources

- **Official Documentation**: https://developer.chrome.com/docs/extensions/
- **Manifest V3 Migration**: https://developer.chrome.com/docs/extensions/mv3/intro/
- **API Reference**: https://developer.chrome.com/docs/extensions/reference/
- **Chrome Web Store**: https://chrome.google.com/webstore/devconsole
- **Sample Extensions**: https://github.com/GoogleChrome/chrome-extensions-samples
- **Policy Compliance**: https://developer.chrome.com/docs/webstore/program-policies/

## Workflow Completion Checklist

- [ ] Requirements defined and documented
- [ ] Implementation plan created and approved
- [ ] Project structure created
- [ ] manifest.json configured correctly
- [ ] Icons generated and added
- [ ] Background service worker implemented
- [ ] Content scripts implemented (if needed)
- [ ] Popup UI implemented and styled
- [ ] Storage layer implemented
- [ ] Message passing working correctly
- [ ] All features tested locally
- [ ] Edge cases tested
- [ ] Performance optimized
- [ ] Security review completed
- [ ] Code cleaned and commented
- [ ] README.md created
- [ ] Store assets prepared
- [ ] Extension packaged as ZIP
- [ ] Submitted to Chrome Web Store (if publishing)
- [ ] Post-launch monitoring plan in place
