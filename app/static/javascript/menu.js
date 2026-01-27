(() => {
    // Utility: find menu from trigger's data-menu
    function getMenu(trigger) {
        const sel = trigger.getAttribute('data-menu');
        return sel ? document.querySelector(sel) : null;
    }

    // State
    let openTrigger = null;
    let openMenu = null;
    let originalParent = null;
    let originalNextSibling = null;

    function openDropdown(trigger, menu) {
        if (openMenu) closeDropdown();

        // Store original position so we can restore it
        originalParent = menu.parentNode;
        originalNextSibling = menu.nextSibling;

        // Move menu to body to escape any stacking context issues
        document.body.appendChild(menu);

        menu.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        openTrigger = trigger;
        openMenu = menu;

        // Position menu fixed to viewport
        const rect = trigger.getBoundingClientRect();
        menu.style.position = 'fixed';
        const menuHeight = menu.offsetHeight;
        const desiredTop = rect.bottom + 4;
        if (desiredTop + menuHeight > window.innerHeight - 8) {
            // Not enough room below, open above the trigger instead
            const fallbackTop = rect.top - menuHeight - 4;
            menu.style.top = (fallbackTop < 8 ? 8 : fallbackTop) + 'px';
        } else {
            menu.style.top = desiredTop + 'px';
        }
        menu.style.left = '';
        menu.style.right = '';
        // Align right edge of menu to right edge of trigger
        if (menu.classList.contains('menu-right')) {
            menu.style.right = (window.innerWidth - rect.right) + 'px';
        } else {
            menu.style.left = rect.left + 'px';
        }
        menu.style.zIndex = '10100';

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
        openMenu.style.position = '';
        openMenu.style.top = '';
        openMenu.style.left = '';
        openMenu.style.right = '';
        openMenu.style.zIndex = '';

        // Move menu back to its original location
        if (originalParent) {
            if (originalNextSibling) {
                originalParent.insertBefore(openMenu, originalNextSibling);
            } else {
                originalParent.appendChild(openMenu);
            }
        }

        if (openTrigger) openTrigger.setAttribute('aria-expanded', 'false');
        document.removeEventListener('click', onDocClick, true);
        document.removeEventListener('keydown', onKeyDown, true);
        window.removeEventListener('scroll', closeDropdown, true);
        openTrigger = null;
        openMenu = null;
        originalParent = null;
        originalNextSibling = null;
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

            if (action === 'add-document') {
                showChatDocumentUpload();
                closeDropdown();
                return;
            }

            if (action === 'add-website') {
                showChatInputModal();
                closeDropdown();
                return;
            }

            return; // unknown action is still swallowed
        }

        // 3) Clicked inside menu on a menu-item without data-action → let onclick fire
        //    The menu-anchor's onclick="event.stopPropagation()" handles blocking the row
        if (inMenu && e.target.closest('.menu-item')) {
            // Don't stop propagation here - let inline onclick handlers fire
            // Close the dropdown after a short delay to allow the action to complete
            setTimeout(closeDropdown, 50);
        }

        // 4) Else: let it fall through (outside-click handler will close it)
    }, true); // ← CAPTURE PHASE

    // Close dropdown when any modal becomes visible
    const modalObserver = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                const el = mutation.target;
                if (el.classList.contains('modal') && window.getComputedStyle(el).display !== 'none') {
                    closeDropdown();
                    return;
                }
            }
        }
    });

    // Observe all modals for style changes (display: none -> block)
    document.querySelectorAll('.modal').forEach(modal => {
        modalObserver.observe(modal, { attributes: true, attributeFilter: ['style'] });
    });

    // Also observe for dynamically added modals
    const bodyObserver = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === 1 && node.classList?.contains('modal')) {
                    modalObserver.observe(node, { attributes: true, attributeFilter: ['style'] });
                }
            });
        }
    });
    bodyObserver.observe(document.body, { childList: true, subtree: true });

})();
