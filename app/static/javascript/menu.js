
(() => {
// Utility: find menu from trigger's data-menu
function getMenu(trigger) {
    const sel = trigger.getAttribute('data-menu');
    return sel ? document.querySelector(sel) : null;
}

// State
let openTrigger = null;
let openMenu = null;

function openDropdown(trigger, menu) {
    if (openMenu) closeDropdown();
    menu.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    openTrigger = trigger;
    openMenu = menu;

    // Focus first item
    const first = menu.querySelector('.menu-item:not([disabled])');
    if (first) first.focus();

    document.addEventListener('click', onDocClick, true);
    document.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('resize', closeDropdown, { once: true });
    window.addEventListener('scroll', closeDropdown, true);
}

function closeDropdown() {
    if (!openMenu) return;
    openMenu.hidden = true;
    if (openTrigger) openTrigger.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', onDocClick, true);
    document.removeEventListener('keydown', onKeyDown, true);
    window.removeEventListener('scroll', closeDropdown, true);
    openTrigger = null;
    openMenu = null;
}

function onDocClick(e) {
    if (!openMenu) return;
    if (openMenu.contains(e.target) || e.target === openTrigger) return;
    closeDropdown();
}

function focusItem(items, idx) {
    if (!items.length) return;
    const next = (idx + items.length) % items.length;
    items[next].focus();
}

function onKeyDown(e) {
    if (!openMenu) return;
    const items = Array.from(openMenu.querySelectorAll('.menu-item:not([disabled])'));
    const idx = items.indexOf(document.activeElement);

    if (e.key === 'Escape') {
    e.preventDefault();
    closeDropdown();
    if (openTrigger) openTrigger.focus();
    } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    focusItem(items, Math.max(0, idx) + 1);
    } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    focusItem(items, (idx === -1 ? items.length : idx) - 1);
    } else if (e.key === 'Home') {
    e.preventDefault();
    if (items[0]) items[0].focus();
    } else if (e.key === 'End') {
    e.preventDefault();
    if (items[items.length - 1]) items[items.length - 1].focus();
    }
}

// Attach toggles
document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-menu]');
    if (!t) return;
    e.preventDefault();
    e.stopPropagation();
    const menu = getMenu(t);
    if (!menu) return;
    menu.hidden ? openDropdown(t, menu) : closeDropdown();
});

// Example action hooks (use data-action on .menu-item)
document.addEventListener('click', (e) => {
    const act = e.target.closest('.menu-item[data-action]');
    if (!act) return;

    const action = act.getAttribute('data-action');
    if (action === 'new-folder') {
    const form = document.getElementById('add-form');
    const field = document.getElementById('add-folder-field');
    const name = window.prompt('New folder name');
    if (name && form && field) {
        field.value = name.trim();
        form.submit();
    }
    closeDropdown();
    } else if (action === 'trigger-file-input') {
    const fi = document.getElementById('file-input');
    if (fi) fi.click();
    closeDropdown();
    } else if (action === 'download-pdf' || action === 'download-csv' || action === 'download-text') {
    // Replace with your handlers
    console.log('Do action:', action);
    closeDropdown();
    }
});
})();
