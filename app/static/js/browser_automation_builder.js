let actions = [];
let actionIdCounter = 0;

function addAction(actionType) {
    const actionId = `action-${actionIdCounter++}`;
    const action = {
        action_id: actionId,
        type: actionType,
        config: getDefaultConfigForAction(actionType)
    };

    actions.push(action);
    renderActions();
}

function getDefaultConfigForAction(actionType) {
    switch (actionType) {
        case 'navigate':
            return { url: '', wait_for: null };
        case 'ensure_login':
            return {
                detection_rules: { url_pattern: '', element_selector: '' },
                instruction_to_user: ''
            };
        case 'fill_form':
            return { fields: [], options: { clear_before: true } };
        case 'click':
            return { locator: { strategy: 'css', value: '' } };
        case 'wait_for':
            return { condition_type: 'element_present', condition_value: '', timeout_ms: 5000 };
        case 'extract':
            return { extraction_spec: { mode: 'simple', fields: [] } };
        default:
            return {};
    }
}

function renderActions() {
    const container = document.getElementById('actions-list');
    container.innerHTML = '';

    if (actions.length === 0) {
        container.innerHTML = '<p class="text-muted">No actions configured yet</p>';
        return;
    }

    actions.forEach((action, index) => {
        const actionEl = createActionElement(action, index);
        container.appendChild(actionEl);
    });
}

function createActionElement(action, index) {
    const div = document.createElement('div');
    div.className = 'action-item card mb-2';
    div.innerHTML = `
        <div class="card-header d-flex justify-content-between align-items-center">
            <span>
                <strong>${index + 1}.</strong>
                ${getActionIcon(action.type)}
                ${getActionLabel(action.type)}
            </span>
            <div>
                <button class="btn btn-sm btn-outline-secondary" onclick="editAction(${index})">
                    <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="removeAction(${index})">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
        <div class="card-body">
            ${renderActionConfig(action)}
        </div>
    `;

    return div;
}

function getActionIcon(type) {
    const icons = {
        navigate: '<i class="bi bi-arrow-right-circle"></i>',
        ensure_login: '<i class="bi bi-shield-check"></i>',
        fill_form: '<i class="bi bi-input-cursor-text"></i>',
        click: '<i class="bi bi-cursor"></i>',
        wait_for: '<i class="bi bi-hourglass"></i>',
        extract: '<i class="bi bi-download"></i>'
    };
    return icons[type] || '';
}

function getActionLabel(type) {
    const labels = {
        navigate: 'Navigate',
        ensure_login: 'Ensure User Login',
        fill_form: 'Fill Form',
        click: 'Click',
        wait_for: 'Wait For',
        extract: 'Extract Data'
    };
    return labels[type] || type;
}

function renderActionConfig(action) {
    switch (action.type) {
        case 'navigate':
            return `
                <div class="form-group mb-0">
                    <label>URL</label>
                    <input type="url" class="form-control form-control-sm"
                           value="${action.config.url || ''}"
                           onchange="updateActionConfig('${action.action_id}', 'url', this.value)" />
                    <small class="text-muted">Supports template variables: {{previous_step.field}}</small>
                </div>
            `;

        case 'ensure_login':
            return `
                <div class="form-group">
                    <label>Instructions for User</label>
                    <textarea class="form-control form-control-sm" rows="2"
                              onchange="updateActionConfig('${action.action_id}', 'instruction_to_user', this.value)"
                    >${action.config.instruction_to_user || ''}</textarea>
                </div>
                <div class="form-group mb-0">
                    <label>Login Detection (URL pattern or element selector)</label>
                    <input type="text" class="form-control form-control-sm"
                           value="${action.config.detection_rules?.url_pattern || ''}"
                           placeholder="^https://example\\.com/dashboard"
                           onchange="updateActionConfig('${action.action_id}', 'detection_url_pattern', this.value)" />
                </div>
            `;

        case 'fill_form':
            return `
                <div class="form-group mb-0">
                    <label>Form Fields</label>
                    <div id="fields-${action.action_id}">
                        ${renderFormFields(action)}
                    </div>
                    <button class="btn btn-sm btn-outline-primary mt-2"
                            onclick="addFormField('${action.action_id}')">
                        Add Field
                    </button>
                </div>
            `;

        case 'click':
            return `
                <div class="form-group mb-0">
                    <label>Element Selector</label>
                    <div class="input-group input-group-sm">
                        <input type="text" class="form-control"
                               value="${action.config.locator?.value || ''}"
                               placeholder="button[type='submit']"
                               onchange="updateActionConfig('${action.action_id}', 'selector', this.value)" />
                        <button class="btn btn-outline-secondary"
                                onclick="pickElement('${action.action_id}')">
                            <i class="bi bi-cursor"></i> Pick
                        </button>
                    </div>
                </div>
            `;

        case 'extract':
            return `
                <div class="form-group mb-0">
                    <label>Fields to Extract</label>
                    <div id="extract-fields-${action.action_id}">
                        ${renderExtractFields(action)}
                    </div>
                    <button class="btn btn-sm btn-outline-primary mt-2"
                            onclick="addExtractField('${action.action_id}')">
                        Add Field
                    </button>
                </div>
            `;

        default:
            return '<p class="text-muted mb-0">No additional configuration needed</p>';
    }
}

function renderFormFields(action) {
    const fields = action.config.fields || [];

    if (fields.length === 0) {
        return '<p class="text-muted">No fields configured</p>';
    }

    return fields.map((field, i) => `
        <div class="input-group input-group-sm mb-1">
            <input type="text" class="form-control" placeholder="Selector"
                   value="${field.locator?.value || ''}" />
            <input type="text" class="form-control" placeholder="Value or {{variable}}"
                   value="${field.value || ''}" />
            <button class="btn btn-outline-danger"
                    onclick="removeFormField('${action.action_id}', ${i})">
                <i class="bi bi-x"></i>
            </button>
        </div>
    `).join('');
}

function renderExtractFields(action) {
    const fields = action.config.extraction_spec?.fields || [];

    if (fields.length === 0) {
        return '<p class="text-muted">No extraction fields configured</p>';
    }

    return fields.map((field, i) => `
        <div class="input-group input-group-sm mb-1">
            <input type="text" class="form-control" placeholder="Field name"
                   value="${field.name || ''}" />
            <input type="text" class="form-control" placeholder="Selector"
                   value="${field.locator?.value || ''}" />
            <select class="form-control">
                <option value="innerText" ${field.attribute === 'innerText' ? 'selected' : ''}>Text</option>
                <option value="innerHTML" ${field.attribute === 'innerHTML' ? 'selected' : ''}>HTML</option>
                <option value="href" ${field.attribute === 'href' ? 'selected' : ''}>Link</option>
                <option value="src" ${field.attribute === 'src' ? 'selected' : ''}>Image</option>
            </select>
            <button class="btn btn-outline-danger"
                    onclick="removeExtractField('${action.action_id}', ${i})">
                <i class="bi bi-x"></i>
            </button>
        </div>
    `).join('');
}

function updateActionConfig(actionId, key, value) {
    const action = actions.find(a => a.action_id === actionId);
    if (!action) return;

    // Handle nested config keys
    if (key === 'url') {
        action.config.url = value;
    } else if (key === 'selector') {
        action.config.locator = { strategy: 'css', value: value };
    } else if (key === 'detection_url_pattern') {
        action.config.detection_rules = action.config.detection_rules || {};
        action.config.detection_rules.url_pattern = value;
    } else if (key === 'instruction_to_user') {
        action.config.instruction_to_user = value;
    }

    renderActions();
}

function removeAction(index) {
    actions.splice(index, 1);
    renderActions();
}

function pickElement(actionId) {
    // Send message to extension to enable element picker
    alert('Element picker feature: Click on any element in the controlled tab to select it');
    // TODO: Implement actual element picker integration
}

function saveBrowserAutomationStep() {
    const initialUrl = document.getElementById('initial-url').value;
    const allowedDomains = document.getElementById('allowed-domains').value
        .split(',')
        .map(d => d.trim())
        .filter(d => d.length > 0);

    const summarizationEnabled = document.getElementById('enable-summarization').checked;
    const summaryPrompt = document.getElementById('summary-prompt').value;
    const model = document.getElementById('model-select').value;

    // Add initial navigate action if URL provided
    if (initialUrl && !actions.some(a => a.type === 'navigate')) {
        actions.unshift({
            action_id: `action-initial`,
            type: 'navigate',
            config: { url: initialUrl }
        });
    }

    const stepData = {
        workflow_step_id: '{{ workflow_step.id }}',
        actions: actions,
        summarization: {
            enabled: summarizationEnabled,
            prompt_template: summaryPrompt
        },
        allowed_domains: allowedDomains,
        model: model,
        timeout_seconds: 300
    };

    // Save via AJAX
    fetch('/workflows/add_browser_automation_step', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(stepData)
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Close modal and refresh
                $('#browserAutomationModal').modal('hide');
                location.reload();
            } else {
                alert('Error saving step: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to save browser automation step');
        });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    renderActions();

    // Toggle summarization config visibility
    document.getElementById('enable-summarization').addEventListener('change', (e) => {
        document.getElementById('summarization-config').style.display =
            e.target.checked ? 'block' : 'none';
    });
});
