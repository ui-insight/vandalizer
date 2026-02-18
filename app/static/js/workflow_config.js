/**
 * workflow_config.js
 * Handles workflow configuration UI for Input/Output settings
 */

let workflowFolders = [];
let currentWorkflowId = null;
let fixedDocuments = []; // Array of {uuid, title, extension}

/**
 * Initialize workflow configuration from backend data
 */
function initializeWorkflowConfig(config) {
    const { workflow_id, input_config, output_config, available_folders } = config;
    currentWorkflowId = workflow_id;
    workflowFolders = available_folders || [];

    // Populate folder selects
    populateFolderSelects();

    // Load Input Config
    if (input_config) {
        loadInputConfig(input_config);
    }

    // Load Output Config
    if (output_config) {
        loadOutputConfig(output_config);
    }
}

/**
 * Populate folder selection dropdowns
 */
/**
 * Populate folder selection dropdowns
 */
function populateFolderSelects() {
    const $folderWatchList = $('#folder-watch-list');
    const $storageSelect = $('#storage-destination-folder');

    // Clear loading message
    $folderWatchList.empty();

    if (workflowFolders.length === 0) {
        $folderWatchList.html('<div style="color: #6b7280; font-size: 13px; font-style: italic; padding: 10px;">No folders found. Please create a folder in the Library first.</div>');
        return;
    }

    workflowFolders.forEach(folder => {
        // Populate inputs checkbox list
        const checkboxId = `folder-check-${folder.uuid}`;
        const pathSpan = (folder.path && folder.path !== folder.title)
            ? `<span style="color: #9ca3af; font-size: 11px; font-weight: 400;">(${folder.path})</span>`
            : '';

        const checkboxItem = `
            <label class="folder-item" style="margin-bottom: 4px; padding: 4px; border-radius: 4px; display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 8px; align-items: center; cursor: pointer; user-select: none;">
                <input type="checkbox" value="${folder.uuid}" class="folder-check-${folder.uuid} folder-watch-checkbox" style="margin: 0; cursor: pointer;">
                <div style="font-size: 13px; color: #374151; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    <i class="fa-solid fa-folder" style="color: #5f6368; margin-right: 8px; font-size: 14px; vertical-align: middle;"></i>
                    <span style="font-weight: 500; margin-right: 6px; vertical-align: middle;">${folder.title}</span>
                    ${pathSpan ? `<span style="vertical-align: middle;">${pathSpan}</span>` : ''}
                </div>
            </label>
        `;
        $folderWatchList.append(checkboxItem);

        // Populate storage select (keep as dropdown for single selection)
        const option = `<option value="${folder.uuid}">${folder.path || folder.title}</option>`;
        $storageSelect.append(option);
    });
}

/**
 * Load input configuration into UI
 */
function loadInputConfig(inputConfig) {
    // Fixed documents
    const fixedDocs = inputConfig.fixed_documents || [];
    fixedDocuments = fixedDocs;
    renderFixedDocsList();

    const folderWatch = inputConfig.folder_watch || {};

    // Folder watch enabled
    if (folderWatch.enabled) {
        $('#folder-watch-enabled').prop('checked', true).trigger('change');
    }

    // Watched folders
    if (folderWatch.folders && folderWatch.folders.length > 0) {
        folderWatch.folders.forEach(folderId => {
            $(`.folder-check-${folderId}`).prop('checked', true);
        });
        // Trigger generic change event to update badges
        $(document).trigger('change');
    }

    // Delay
    if (folderWatch.delay_seconds) {
        $('#folder-watch-delay').val(folderWatch.delay_seconds);
    }

    // File filters
    const fileFilters = folderWatch.file_filters || {};
    if (fileFilters.types && fileFilters.types.length > 0) {
        fileFilters.types.forEach(type => {
            $(`.file-type-filter[value="${type}"]`).prop('checked', true);
        });
    }

    // Exclude patterns
    if (fileFilters.exclude_patterns && fileFilters.exclude_patterns.length > 0) {
        $('#folder-watch-exclude').val(fileFilters.exclude_patterns.join(', '));
    }

    // Batch mode
    if (folderWatch.batch_mode) {
        $('#folder-watch-batch-mode').val(folderWatch.batch_mode);
    }
}

/**
 * Load output configuration into UI
 */
function loadOutputConfig(outputConfig) {
    // Storage
    const storage = outputConfig.storage || {};
    if (storage.enabled) {
        $('#storage-enabled').prop('checked', true).trigger('change');
    }
    if (storage.destination_folder) {
        $('#storage-destination-folder').val(storage.destination_folder);
    }
    if (storage.format) {
        $('#storage-format').val(storage.format);
    }
    if (storage.file_naming) {
        $('#storage-filename').val(storage.file_naming);
    }

    // Notifications
    const notifications = outputConfig.notifications || [];
    notifications.forEach(notification => {
        addNotificationFromData(notification);
    });
}

/**
 * Add notification from data object
 */
function addNotificationFromData(notification) {
    const template = $('#notification-template').html();
    const $notification = $(template);

    $notification.find('.notification-channel').val(notification.channel || 'email');
    $notification.find('.notification-recipients').val((notification.recipients || []).join(', '));
    $notification.find('.notification-notify-owner').prop('checked', notification.notify_owner || false);
    $notification.find('.notification-conditions').val(notification.conditions || 'always');
    $notification.find('.notification-include-summary').prop('checked', notification.include_summary !== false);

    $('#notifications-list').append($notification);
    $('#no-notifications-message').hide();
}

/**
 * Collect input configuration from UI
 */
function collectInputConfig() {
    const inputConfig = {
        manual_enabled: true, // Always enabled
        fixed_documents: fixedDocuments.map(doc => ({
            uuid: doc.uuid,
            title: doc.title
        })),
        folder_watch: {
            enabled: $('#folder-watch-enabled').is(':checked'),
            folders: $('.folder-watch-checkbox:checked').map(function () {
                return $(this).val();
            }).get(),
            delay_seconds: parseInt($('#folder-watch-delay').val()) || 300,
            file_filters: {
                types: $('.file-type-filter:checked').map(function () {
                    return $(this).val();
                }).get(),
                exclude_patterns: $('#folder-watch-exclude').val()
                    .split(',')
                    .map(p => p.trim())
                    .filter(p => p.length > 0)
            },
            batch_mode: $('#folder-watch-batch-mode').val() || 'per_document'
        },
        conditions: [] // MVP doesn't support conditions yet
    };

    return inputConfig;
}

/**
 * Collect output configuration from UI
 */
function collectOutputConfig() {
    const outputConfig = {
        storage: {
            enabled: $('#storage-enabled').is(':checked'),
            destination_folder: $('#storage-destination-folder').val(),
            file_naming: $('#storage-filename').val() || '{date}_{workflow_name}_results',
            format: $('#storage-format').val() || 'csv',
            append_mode: false // MVP doesn't support append mode yet
        },
        notifications: []
    };

    // Collect all notifications
    $('.notification-item').each(function () {
        const $item = $(this);
        const notification = {
            channel: $item.find('.notification-channel').val(),
            recipients: $item.find('.notification-recipients').val()
                .split(',')
                .map(r => r.trim())
                .filter(r => r.length > 0),
            notify_owner: $item.find('.notification-notify-owner').is(':checked'),
            notify_team: false, // MVP doesn't support team notifications yet
            conditions: $item.find('.notification-conditions').val(),
            include_summary: $item.find('.notification-include-summary').is(':checked'),
            include_full_results: false // MVP doesn't show full results in email
        };
        outputConfig.notifications.push(notification);
    });

    return outputConfig;
}

/**
 * Save workflow configuration to backend
 */
function saveWorkflowConfiguration(workflowId) {
    const inputConfig = collectInputConfig();
    const outputConfig = collectOutputConfig();

    // Basic validation
    if (inputConfig.folder_watch.enabled && inputConfig.folder_watch.folders.length === 0) {
        alert('Please select at least one folder to watch.');
        $('.workflow-tab[data-tab="input"]').click();
        return;
    }

    if (outputConfig.storage.enabled && !outputConfig.storage.destination_folder) {
        alert('Please select a destination folder for storage.');
        $('.workflow-tab[data-tab="output"]').click();
        return;
    }

    const data = {
        workflow_id: workflowId,
        name: $('#newWorkflowName').val(),
        description: $('#newWorkflowDescription').val(),
        input_config: inputConfig,
        output_config: outputConfig
    };

    $.ajax({
        url: '/workflows/save_configuration',
        type: 'POST',
        data: JSON.stringify(data),
        contentType: 'application/json; charset=utf-8',
        dataType: 'json',
        async: true,
        success: function (response) {
            console.log('Configuration saved:', response);
            // Redirect back to library
            const url = new URL(window.location.href);
            url.searchParams.set('section', 'Library');
            location.href = url.toString();
        },
        error: function (xhr, ajaxOptions, thrownError) {
            console.error('Save failed:', xhr.status, thrownError);
            alert('Failed to save configuration. Please try again.');
        }
    });
}

/**
 * Render the list of selected fixed documents
 */
function renderFixedDocsList() {
    const $list = $('#fixed-docs-list');
    $list.find('.fixed-doc-item').remove();

    if (fixedDocuments.length === 0) {
        $('#fixed-docs-empty').show();
    } else {
        $('#fixed-docs-empty').hide();
        fixedDocuments.forEach(doc => {
            const icon = getFileIcon(doc.extension || 'pdf');
            const item = `
                <div class="fixed-doc-item" data-uuid="${doc.uuid}"
                    style="display: flex; align-items: center; justify-content: space-between;
                           padding: 8px 12px; background: white; border: 1px solid #e5e7eb;
                           border-radius: 6px; margin-bottom: 6px;">
                    <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
                        <i class="${icon}" style="color: #6b7280; flex-shrink: 0;"></i>
                        <span style="font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${doc.title}</span>
                    </div>
                    <button type="button" class="remove-fixed-doc-btn" data-uuid="${doc.uuid}"
                        style="background: none; border: none; color: #9ca3af; cursor: pointer; padding: 4px; flex-shrink: 0;">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
            `;
            $list.append(item);
        });
    }
    updateFixedDocsBadge();
}

/**
 * Get Font Awesome icon class for file extension
 */
function getFileIcon(ext) {
    const icons = {
        'pdf': 'fa-solid fa-file-pdf',
        'docx': 'fa-solid fa-file-word',
        'xlsx': 'fa-solid fa-file-excel',
        'xls': 'fa-solid fa-file-excel',
        'html': 'fa-solid fa-file-code',
    };
    return icons[ext] || 'fa-solid fa-file';
}

/**
 * Update the fixed docs count badge
 */
function updateFixedDocsBadge() {
    const count = fixedDocuments.length;
    const $badge = $('#fixed-docs-count');
    $badge.text(`${count} document${count !== 1 ? 's' : ''}`);
    if (count > 0) {
        $badge.css({ 'background': '#d1fae5', 'color': '#065f46' });
    } else {
        $badge.css({ 'background': '#dbeafe', 'color': '#1e40af' });
    }
    // Also update the main input tab badge
    if (typeof updateInputBadge === 'function') {
        updateInputBadge();
    }
}

/**
 * Search documents via AJAX
 */
let searchTimeout = null;
function searchDocuments(query) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        $.ajax({
            url: '/workflows/search_documents',
            type: 'POST',
            data: JSON.stringify({ query: query }),
            contentType: 'application/json',
            dataType: 'json',
            success: function (response) {
                renderSearchResults(response.documents || []);
            }
        });
    }, 300);
}

/**
 * Render search results in the dropdown
 */
function renderSearchResults(documents) {
    const $results = $('#fixed-docs-search-results');
    $results.empty();

    if (documents.length === 0) {
        $results.html('<div style="color: #9ca3af; font-size: 13px; text-align: center; padding: 20px;">No documents found.</div>');
        return;
    }

    const existingUuids = fixedDocuments.map(d => d.uuid);

    documents.forEach(doc => {
        const isAlreadyAdded = existingUuids.includes(doc.uuid);
        const icon = getFileIcon(doc.extension);
        const item = `
            <div class="fixed-doc-search-item" data-uuid="${doc.uuid}"
                data-title="${doc.title}" data-extension="${doc.extension || 'pdf'}"
                style="padding: 10px 12px; cursor: ${isAlreadyAdded ? 'default' : 'pointer'};
                       border-bottom: 1px solid #f3f4f6; display: flex;
                       align-items: center; gap: 8px;
                       ${isAlreadyAdded ? 'opacity: 0.5;' : ''}">
                <i class="${icon}" style="color: #6b7280;"></i>
                <span style="font-size: 13px;">${doc.title}</span>
                ${isAlreadyAdded ? '<span style="font-size: 11px; color: #9ca3af; margin-left: auto;">Added</span>' : ''}
            </div>
        `;
        $results.append(item);
    });
}

// Export for use in templates
window.initializeWorkflowConfig = initializeWorkflowConfig;
window.saveWorkflowConfiguration = saveWorkflowConfiguration;
