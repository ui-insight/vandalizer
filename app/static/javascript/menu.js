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
    items.length && items[(Math.max(0, idx) + 1) % items.length].focus();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    items.length && items[(idx === -1 ? items.length : idx) - 1]?.focus();
  } else if (e.key === 'Home') {
    e.preventDefault();
    items[0]?.focus();
  } else if (e.key === 'End') {
    e.preventDefault();
    items[items.length - 1]?.focus();
  }
}

/* ---------------------------
   Single CAPTURE-PHASE router
   --------------------------- */
document.addEventListener('click', function dropdownRouter(e) {
  const trigger = e.target.closest('[data-menu]');
  const menuItem = e.target.closest('.menu-item[data-action]');
  const inMenu = e.target.closest('.menu');

  // 1) Trigger clicked → toggle
  if (trigger) {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    const menu = getMenu(trigger);
    if (!menu) return;
    menu.hidden ? openDropdown(trigger, menu) : closeDropdown();
    return;
  }

  // 2) Action clicked inside menu
  if (menuItem) {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    const action = menuItem.getAttribute('data-action');
    if (action === 'new-folder' || action === 'new-team-folder') {
      const form = document.getElementById('add-form');
      const field = document.getElementById('add-folder-field');
      const name = window.prompt(action === 'new-folder' ? 'New folder name' : 'New team folder name');
      if (name && form && field) {
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'folder_type';
        hidden.value = (action === 'new-folder') ? 'individual' : 'team';
        form.appendChild(hidden);
        field.value = name.trim();
        form.submit();
      }
      closeDropdown();
      return;
    }

    if (action === 'trigger-file-input') {
      document.getElementById('file-input')?.click();
      closeDropdown();
      return;
    }

    if (action === 'download-pdf' || action === 'download-csv' || action === 'download-text') {
      console.log('Do action:', action);
      closeDropdown();
      return;
    }

    return; // unknown action is still swallowed
  }

  // 3) Clicked inside menu but not on an actionable item → swallow so cards don't see it
  if (inMenu) {
    e.stopPropagation();
    e.stopImmediatePropagation();
    return;
  }

  // 4) Else: let it fall through (outside-click handler will close it)
}, true); // ← CAPTURE PHASE

})();
