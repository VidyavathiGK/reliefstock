/**
 * ReliefStock - Enterprise NGO Frontend Helper Scripts
 * Zero external dependencies: pure vanilla modern JavaScript.
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Sidebar Navigation Drawer Toggle
    const sidebar = document.getElementById('appSidebar');
    const toggleBtn = document.getElementById('sidebarToggleBtn');
    const overlay = document.getElementById('sidebarOverlay');

    function openSidebar() {
        if (sidebar && overlay) {
            sidebar.classList.add('is-open');
            overlay.classList.add('is-active');
            document.body.style.overflow = 'hidden';
        }
    }

    function closeSidebar() {
        if (sidebar && overlay) {
            sidebar.classList.remove('is-open');
            overlay.classList.remove('is-active');
            document.body.style.overflow = '';
        }
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (sidebar.classList.contains('is-open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
    }

    if (overlay) {
        overlay.addEventListener('click', closeSidebar);
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSidebar();
        }
    });

    // 2. Client-side Table Search & Filter helper
    const searchInputs = document.querySelectorAll('[data-table-search]');
    searchInputs.forEach((input) => {
        const targetTableId = input.getAttribute('data-table-search');
        const targetTable = document.getElementById(targetTableId);
        if (!targetTable) return;

        input.addEventListener('input', () => {
            const query = input.value.toLowerCase().trim();
            const rows = targetTable.querySelectorAll('tbody tr:not(.empty-row)');
            let matchCount = 0;

            rows.forEach((row) => {
                const text = row.innerText.toLowerCase();
                const matches = text.includes(query);
                row.style.display = matches ? '' : 'none';
                if (matches) matchCount++;
            });

            // Toggle no-results row
            let noResultRow = targetTable.querySelector('.search-no-results');
            if (matchCount === 0 && query !== '') {
                if (!noResultRow) {
                    noResultRow = document.createElement('tr');
                    noResultRow.className = 'search-no-results';
                    const colCount = targetTable.querySelectorAll('thead th').length || 6;
                    noResultRow.innerHTML = `<td colspan="${colCount}" style="text-align: center; padding: 28px; color: #64748b; font-style: italic;">No matching items found for "${input.value}"</td>`;
                    targetTable.querySelector('tbody').appendChild(noResultRow);
                }
                noResultRow.style.display = '';
            } else if (noResultRow) {
                noResultRow.style.display = 'none';
            }
        });
    });

    // 3. Dropdown Filter Helper (e.g. category or status filter)
    const filterSelects = document.querySelectorAll('[data-table-filter]');
    filterSelects.forEach((select) => {
        const targetTableId = select.getAttribute('data-table-filter');
        const colIndex = parseInt(select.getAttribute('data-filter-col') || '1', 10);
        const targetTable = document.getElementById(targetTableId);
        if (!targetTable) return;

        select.addEventListener('change', () => {
            const filterVal = select.value.toLowerCase().trim();
            const rows = targetTable.querySelectorAll('tbody tr:not(.empty-row):not(.search-no-results)');

            rows.forEach((row) => {
                const cell = row.children[colIndex];
                if (!cell || filterVal === 'all' || filterVal === '') {
                    row.style.display = '';
                } else {
                    const text = cell.innerText.toLowerCase();
                    row.style.display = text.includes(filterVal) ? '' : 'none';
                }
            });
        });
    });

    // 4. Auto-dismiss alerts after 6 seconds
    const autoAlerts = document.querySelectorAll('.alert-auto-dismiss');
    autoAlerts.forEach((alert) => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-6px)';
            setTimeout(() => alert.remove(), 400);
        }, 6000);
    });
});
