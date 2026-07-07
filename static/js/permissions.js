/**
 * permissions.js
 * Alpine.js component for the role permission matrix admin UI.
 * Auto-saves on every checkbox click, no submit button needed.
 */

function permissionsMatrix() {
    return {
        // State
        permissions: {},      // role -> Set of permission keys
        saveStatus: null,     // null | 'saving' | 'ok' | 'error'
        highlightedRole: '',
        highlightedRow: '',
        _saveTimer: null,
        _pendingSave: {},     // role -> pending permission array

        // ── Lifecycle ──────────────────────────────────────────────────────

        init() {
            const cfg = window.__permissionsConfig || {};
            const initial = cfg.initialPermissions || {};

            // Convert arrays to Sets for O(1) lookup
            for (const [role, perms] of Object.entries(initial)) {
                this.permissions[role] = new Set(Array.isArray(perms) ? perms : []);
            }
        },

        // ── Core methods ───────────────────────────────────────────────────

        hasPermission(role, key) {
            return this.permissions[role]?.has(key) ?? false;
        },

        toggle(role, key) {
            if (!this.permissions[role]) {
                this.permissions[role] = new Set();
            }

            // Optimistic UI update
            if (this.permissions[role].has(key)) {
                this.permissions[role].delete(key);
            } else {
                this.permissions[role].add(key);
            }

            // Force Alpine reactivity (Sets aren't reactive by default)
            this.permissions[role] = new Set(this.permissions[role]);

            // Schedule debounced save
            this._scheduleSave(role);
        },

        resetRole(role) {
            if (!confirm(`¿Restablecer los permisos de "${role}" a los valores predeterminados?`)) {
                return;
            }
            // Fetch defaults from server and apply
            fetch(window.__permissionsConfig.apiUrl)
                .then(r => r.json())
                .then(data => {
                    // Server always has defaults loaded; re-fetch after reset
                    this._doSave(role, null); // null = reset to defaults
                });
        },

        // ── Save logic ─────────────────────────────────────────────────────

        _scheduleSave(role) {
            // Accumulate changes per role; batch saves within 400ms
            if (!this._pendingSave[role]) {
                this._pendingSave[role] = true;
            }

            clearTimeout(this._saveTimer);
            this._saveTimer = setTimeout(() => {
                const rolesToSave = Object.keys(this._pendingSave);
                this._pendingSave = {};
                rolesToSave.forEach(r => this._doSave(r, [...this.permissions[r]]));
            }, 400);
        },

        async _doSave(role, permArray) {
            this.saveStatus = 'saving';
            const url = (window.__permissionsConfig.saveUrl || '/users/permissions/') + role;
            const body = permArray !== null
                ? { permissions: permArray }
                : { permissions: [], reset: true };

            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
                    },
                    body: JSON.stringify(body),
                });

                const data = await resp.json();

                if (resp.ok && data.success) {
                    this.saveStatus = 'ok';
                } else {
                    console.error('[Permissions] Save error:', data);
                    this.saveStatus = 'error';
                }
            } catch (err) {
                console.error('[Permissions] Network error:', err);
                this.saveStatus = 'error';
            }

            // Auto-clear status badge after 2 seconds
            setTimeout(() => { this.saveStatus = null; }, 2000);
        },
    };
}
