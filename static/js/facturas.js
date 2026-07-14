/* ══════════════════════════════════════════════════════
   facturas.js — Alpine.js app logic for the Facturas page
   Extracted from templates/orders/facturas.html
   
   Server-side values are injected via window.__facturasConfig
   which is set in the template before this script loads.
   ══════════════════════════════════════════════════════ */

window.estadoCuentaWindowApp = function(winConfig) {
    return {
        id: winConfig.id,
        customerCode: winConfig.customerCode,
        customerName: winConfig.customerName,
        
        show: true,
        minimized: false,
        loading: true,
        data: null,
        selected: [],
        filterSearch: '',
        filterCurrency: 'ALL',
        filterOverdue: 'ALL',
        
        sortColumn: 'doc_num',
        sortDir: 'desc',

        // Window positioning state
        ecWinCollapsed: false,
        ecWinDragging: false,
        ecWinX: winConfig.startX || 80,
        ecWinY: winConfig.startY || 80,
        ecWinOffsetX: 0,
        ecWinOffsetY: 0,
        _ecWinOnDrag: null,
        _ecWinStopDrag: null,

        // Window Z-Index to bring active window to front
        zIndex: winConfig.zIndex || 9999,

        async init() {
            // Setup Drag handlers
            this._ecWinOnDrag = (e) => {
                if (!this.ecWinDragging) return;
                e.preventDefault();
                this.ecWinX = Math.max(0, Math.min(e.clientX - this.ecWinOffsetX, window.innerWidth - 200));
                this.ecWinY = Math.max(0, Math.min(e.clientY - this.ecWinOffsetY, window.innerHeight - 50));
            };
            this._ecWinStopDrag = () => {
                this.ecWinDragging = false;
                document.removeEventListener('mousemove', this._ecWinOnDrag);
                document.removeEventListener('mouseup', this._ecWinStopDrag);
            };

            // Fetch data
            try {
                const res = await fetch(`/orders/api/facturas/estado-cuenta/${this.customerCode}`);
                const data = await res.json();
                if (data.success && data.data) {
                    this.data = data.data;
                    this.selected = data.data.invoices.map(i => i.doc_num);
                } else {
                    alert(data.error || 'Error al obtener estado de cuenta');
                    this.close();
                }
            } catch (e) {
                console.error('Error fetching account statement:', e);
                alert('Error de conexión');
                this.close();
            } finally {
                this.loading = false;
            }
        },

        ecWinStartDrag(e) {
            this.$dispatch('bring-estado-cuenta-front', { id: this.id });
            this.ecWinDragging = true;
            const rect = this.$refs.ecWindow.getBoundingClientRect();
            this.ecWinOffsetX = e.clientX - rect.left;
            this.ecWinOffsetY = e.clientY - rect.top;
            document.addEventListener('mousemove', this._ecWinOnDrag);
            document.addEventListener('mouseup', this._ecWinStopDrag);
        },

        close() {
            // If the parent facturasApp provides closeEstadoCuenta, call it directly
            if (typeof this.closeEstadoCuenta === 'function') {
                this.closeEstadoCuenta(this.id);
            } else {
                this.$dispatch('close-estado-cuenta', { id: this.id });
            }
        },

        toggleInvoice(docNum) {
            const idx = this.selected.indexOf(docNum);
            if (idx >= 0) this.selected.splice(idx, 1);
            else this.selected.push(docNum);
        },

        filteredInvoices() {
            if (!this.data) return [];
            let result = this.data.invoices.filter(inv => {
                if (this.filterSearch && !String(inv.doc_num).includes(this.filterSearch.trim())) return false;
                if (this.filterCurrency !== 'ALL' && (inv.currency || 'MXN').toUpperCase() !== this.filterCurrency) return false;
                if (this.filterOverdue === 'OVERDUE' && inv.days_overdue <= 0) return false;
                if (this.filterOverdue === 'CURRENT' && inv.days_overdue > 0) return false;
                return true;
            });

            result.sort((a, b) => {
                let valA = a[this.sortColumn];
                let valB = b[this.sortColumn];
                
                if (valA === undefined || valA === null) valA = '';
                if (valB === undefined || valB === null) valB = '';

                if (this.sortColumn === 'doc_date' || this.sortColumn === 'due_date') {
                    // Dates might be 'YYYY-MM-DD HH:MM:SS'
                    valA = valA ? new Date(String(valA).split(' ')[0]).getTime() : 0;
                    valB = valB ? new Date(String(valB).split(' ')[0]).getTime() : 0;
                } else if (this.sortColumn === 'balance' || this.sortColumn === 'doc_num' || this.sortColumn === 'days_overdue') {
                    valA = Number(valA) || 0;
                    valB = Number(valB) || 0;
                } else {
                    valA = String(valA).toLowerCase();
                    valB = String(valB).toLowerCase();
                }

                if (valA < valB) return this.sortDir === 'asc' ? -1 : 1;
                if (valA > valB) return this.sortDir === 'asc' ? 1 : -1;
                return 0;
            });

            return result;
        },

        sortBy(column) {
            if (this.sortColumn === column) {
                this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortColumn = column;
                this.sortDir = 'desc'; // Default to desc
            }
        },

        toggleAll() {
            const filtered = this.filteredInvoices();
            const filteredNums = filtered.map(i => i.doc_num);
            const allFilteredSelected = filteredNums.every(n => this.selected.includes(n));
            if (allFilteredSelected) {
                this.selected = this.selected.filter(n => !filteredNums.includes(n));
            } else {
                const newSet = new Set([...this.selected, ...filteredNums]);
                this.selected = [...newSet];
            }
        },

        allSelected() {
            const filtered = this.filteredInvoices();
            if (filtered.length === 0) return false;
            return filtered.every(i => this.selected.includes(i.doc_num));
        },

        selectedCount() {
            return this.selected.length;
        },

        selectedTotalMXN() {
            if (!this.data) return 0;
            return this.data.invoices
                .filter(i => this.selected.includes(i.doc_num) && (i.currency || 'MXN').toUpperCase() !== 'USD')
                .reduce((s, i) => s + i.balance, 0);
        },

        selectedTotalUSD() {
            if (!this.data) return 0;
            return this.data.invoices
                .filter(i => this.selected.includes(i.doc_num) && (i.currency || 'MXN').toUpperCase() === 'USD')
                .reduce((s, i) => s + i.balance, 0);
        },

        generate() {
            if (this.selectedCount() === 0) return;
            const invoices = this.selected.join(',');
            const url = `/orders/estado-cuenta?card_code=${this.customerCode}&invoices=${invoices}`;
            window.open(url, '_blank');
            this.close();
        }
    };
};

function facturasApp() {
    const cfg = window.__facturasConfig || {};
    return {
        // Tab visibility — populated from backend per user role
        tabs: cfg.tabs || { facturas: true, credito: true, relaciones: true, pendientes: true, almacen: true },
        
        invoices: [],
        isInitialized: false,
        stats: {},
        loading: false,
        timer: 30,
        searchQuery: '',
        statusFilter: '',
        sortColumn: 'invoice_number',
        sortDir: 'desc',
        manualOrder: [],
        selectedDate: localStorage.getItem('qb_facturas_date') || new Date().toISOString().split('T')[0],
        lastFetchedDate: localStorage.getItem('qb_facturas_date') || new Date().toISOString().split('T')[0],
        sapAvailable: cfg.sapAvailable,
        canEditFacturas: cfg.canEditFacturas,
        errorMsg: '',
        savedViews: [],
        shippingFilter: '',
        rowColors: {},
        availableColors: ['', 'rojo', 'azul', 'verde', 'amarillo', 'morado', 'rosa', 'gris'],
        extraInvoices: [],
        customCustomerNames: {},
        undoStack: [],
        eventSource: null,
        // Relación de Envíos tracking
        activeTab: (() => {
            // Default to first permitted tab (respects permission config)
            const tabs = cfg.tabs || {};
            const saved = localStorage.getItem('qb_facturas_active_tab');
            const order = ['facturas','credito','relaciones','pendientes','almacen'];
            // Use saved tab if still permitted, else pick first permitted
            if (saved && tabs[saved]) return saved;
            return order.find(t => tabs[t]) || 'facturas';
        })(),
        creditoSubTab: 'Todas',
        
        // Pending Summary Tracking
        pendingSubTab: localStorage.getItem('qb_facturas_pending_subtab') || 'current', // 'calendar', 'all', 'current'
        pendingInvoices: [], // Sub-store for pending invoices across all dates
        pendingSummaryLoading: false,
        pendingSummaryData: [],
        pendingCalendarMonth: new Date().getMonth(),
        pendingCalendarYear: new Date().getFullYear(),
        allPendingExpanded: false,
        
        currentRelacion: null,
        relaciones: [],
        relacionLoading: false,
        relacionDateFrom: new Date(Date.now() - 30*86400000).toISOString().split('T')[0],
        relacionDateTo: new Date().toISOString().split('T')[0],
        autoSaveTimeout: null,
        // Signature state
        currentUserUsername: cfg.currentUserUsername,
        currentUserFullName: cfg.currentUserFullName,
        currentUserSignature: cfg.currentUserSignature,
        signatures: { facturacion: null, credito: null },
        canSignFacturacion: cfg.canSignFacturacion,
        canSignCredito: cfg.canSignCredito,
        canAuthorizarCredito: cfg.canAuthorizarCredito || false,
        clientId: Math.random().toString(36).substring(2) + Date.now().toString(36),
        _suppressRelacionHighlight: false,

        // Context Menu & Relationship Map State
        contextMenuShow: false,
        contextMenuX: 0,
        contextMenuY: 0,
        selectedInvoiceForMenu: null,
        relationshipMapShow: false,
        relationshipMapLoading: false,
        relationshipMapData: null,
        relationshipMapMinimized: false,
        relationshipMapInvoiceNum: null,

        // Order Detail Floating Window State
        orderDetailShow: false,
        orderDetailMinimized: false,
        orderDetailUrl: '',
        orderDetailLabel: '',

        // Estado de Cuenta Windows State
        estadoCuentaWindows: [],

        // Estado de Cuenta Subtab State
        ecSubSearchQuery: '',
        ecSubSearchResults: [],
        ecSubSearchLoading: false,
        ecSubSearchTimeout: null,
        ecSubSelectedClient: null,
        ecSubClientData: null,
        ecSubClientLoading: false,
        ecSubSelectedInvoices: [],
        ecSubFilterCurrency: 'ALL',
        ecSubFilterOverdue: 'ALL',

        // Add Invoice Modal State
        addInvoiceModalOpen: false,
        addInvoiceSearchQuery: '',
        addInvoiceSelectedPending: [],
        addInvoiceManualNum: '',
        addInvoiceManualList: [],
        addInvoiceLoading: false,
        addInvoiceOtherDaysPending: [], // [{date, label, invoices: [...]}]

        showContextMenu(event, inv) {
            if (this.activeTab !== 'facturas' && this.activeTab !== 'credito') return;
            this.selectedInvoiceForMenu = inv;
            this.contextMenuX = event.clientX;
            this.contextMenuY = event.clientY;
            this.contextMenuShow = true;

            // After render, clamp position so menu stays within viewport
            this.$nextTick(() => {
                const menu = document.querySelector('.sao-context-menu');
                if (!menu) return;
                const rect = menu.getBoundingClientRect();
                const vw = window.innerWidth;
                const vh = window.innerHeight;
                const pad = 8; // pixels of margin from edge

                if (rect.bottom > vh - pad) {
                    this.contextMenuY = Math.max(pad, event.clientY - rect.height);
                }
                if (rect.right > vw - pad) {
                    this.contextMenuX = Math.max(pad, event.clientX - rect.width);
                }
            });
        },

        closeRelationshipMap() {
            this.relationshipMapShow = false;
            this.relationshipMapMinimized = false;
        },

        formatDocDate(dateStr) {
            if (!dateStr || dateStr === 'None') return '';
            try {
                const parts = dateStr.split(' ')[0].split('-');
                if (parts.length === 3) {
                    return `${parts[2]}/${parts[1]}/${parts[0]}`;
                }
                return dateStr;
            } catch (e) {
                console.error('Error formatting date:', e);
                return dateStr || '';
            }
        },

        showToast(title, message, icon = '🔔') {
            const container = document.getElementById('qbGlobalToastContainer');
            if (!container) return;

            const toast = document.createElement('div');
            toast.className = 'qb-toast';
            toast.style.pointerEvents = 'auto';
            toast.innerHTML = `
                <div class="qb-toast-icon">${icon}</div>
                <div class="qb-toast-body">
                    <div class="qb-toast-title">${title}</div>
                    <div class="qb-toast-msg">${message}</div>
                    <div class="qb-toast-time">${new Date().toLocaleTimeString('es-MX')}</div>
                </div>
            `;
            container.appendChild(toast);

            setTimeout(() => {
                toast.classList.add('qb-toast-out');
                setTimeout(() => toast.remove(), 300);
            }, 4000);
        },

        copyToClipboard(text, docType) {
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                this.showToast('Copiado', `${docType} #${text} copiado al portapapeles.`, '📋');
            }).catch(err => {
                console.error('Error copying text:', err);
            });
        },

        async openRelationshipMap(invoiceNum) {
            this.contextMenuShow = false;
            this.relationshipMapShow = true;
            this.relationshipMapMinimized = false;
            this.relationshipMapLoading = true;
            this.relationshipMapData = null;
            this.relationshipMapInvoiceNum = invoiceNum;
            try {
                const res = await fetch(`/orders/api/facturas/${invoiceNum}/relationship-map`);
                const data = await res.json();
                if (data.success && data.data) {
                    this.relationshipMapData = data.data;
                } else {
                    alert(data.error || 'Error al obtener el mapa de relaciones');
                    this.relationshipMapShow = false;
                }
            } catch (e) {
                console.error('Error fetching relationship map:', e);
                alert('Error de conexión al obtener el mapa de relaciones');
                this.relationshipMapShow = false;
            } finally {
                this.relationshipMapLoading = false;
            }
        },

        openOrderDetail(orderNumber) {
            this.contextMenuShow = false;
            this.orderDetailUrl = `/orders/${orderNumber}`;
            this.orderDetailLabel = `Pedido #${orderNumber}`;
            this.orderDetailShow = true;
            this.orderDetailMinimized = false;
        },

        closeOrderDetail() {
            this.orderDetailShow = false;
            this.orderDetailMinimized = false;
            this.orderDetailUrl = '';
        },

        // ── Estado de Cuenta Methods ──
        async openEstadoCuenta(customerCode, customerName) {
            this.contextMenuShow = false;
            
            // Check if already open
            const existingWin = this.estadoCuentaWindows.find(w => w.customerCode === customerCode);
            if (existingWin) {
                this.$dispatch('bring-estado-cuenta-front', { id: existingWin.id });
                // Also broadcast an event that will trigger the modal's `minimized = false`
                this.$dispatch('focus-estado-cuenta', { id: existingWin.id });
                return;
            }

            // Calculate cascading spawn position based on number of active windows
            const winCount = this.estadoCuentaWindows.length;
            const startX = 80 + (winCount * 30);
            const startY = 80 + (winCount * 30);
            
            const maxZIndex = this.estadoCuentaWindows.length > 0 
                ? Math.max(...this.estadoCuentaWindows.map(w => w.zIndex || 9999)) 
                : 9999;

            const newWin = {
                id: 'ec_' + Date.now() + '_' + Math.floor(Math.random()*1000),
                customerCode: customerCode,
                customerName: customerName || 'Cliente',
                startX: startX,
                startY: startY,
                zIndex: maxZIndex + 1
            };
            
            this.estadoCuentaWindows.push(newWin);
        },
        
        bringEstadoCuentaToFront(id) {
            const maxZIndex = this.estadoCuentaWindows.length > 0 
                ? Math.max(...this.estadoCuentaWindows.map(w => w.zIndex || 9999)) 
                : 9999;
                
            const winIndex = this.estadoCuentaWindows.findIndex(w => w.id === id);
            if (winIndex >= 0) {
                // If it's not already the highest, make it the highest
                if (this.estadoCuentaWindows[winIndex].zIndex < maxZIndex) {
                    this.estadoCuentaWindows[winIndex].zIndex = maxZIndex + 1;
                }
            }
        },

        closeEstadoCuenta(id) {
            this.estadoCuentaWindows = this.estadoCuentaWindows.filter(w => w.id !== id);
        },

        // ── Estado de Cuenta Subtab Methods ──
        ecSubSearch() {
            const q = this.ecSubSearchQuery.trim();
            if (q.length < 2) {
                this.ecSubSearchResults = [];
                return;
            }
            clearTimeout(this.ecSubSearchTimeout);
            this.ecSubSearchTimeout = setTimeout(async () => {
                this.ecSubSearchLoading = true;
                try {
                    const res = await fetch(`/orders/api/customers/search?q=${encodeURIComponent(q)}`);
                    const json = await res.json();
                    if (json.success) {
                        this.ecSubSearchResults = json.results;
                    }
                } catch (e) {
                    console.error('Customer search error:', e);
                } finally {
                    this.ecSubSearchLoading = false;
                }
            }, 300);
        },

        async ecSubSelectClient(client) {
            this.ecSubSelectedClient = client;
            this.ecSubSearchResults = [];
            this.ecSubSearchQuery = `${client.card_name} (${client.card_code})`;
            this.ecSubClientLoading = true;
            this.ecSubSelectedInvoices = [];
            this.ecSubFilterCurrency = 'ALL';
            this.ecSubFilterOverdue = 'ALL';
            try {
                const res = await fetch(`/orders/api/facturas/estado-cuenta/${client.card_code}`);
                const json = await res.json();
                if (json.success && json.data) {
                    this.ecSubClientData = json.data;
                    // Select all by default
                    this.ecSubSelectedInvoices = json.data.invoices.map(i => i.doc_num);
                } else {
                    this.ecSubClientData = null;
                }
            } catch (e) {
                console.error('Error fetching account statement:', e);
                this.ecSubClientData = null;
            } finally {
                this.ecSubClientLoading = false;
            }
        },

        ecSubClearClient() {
            this.ecSubSelectedClient = null;
            this.ecSubClientData = null;
            this.ecSubSelectedInvoices = [];
            this.ecSubSearchQuery = '';
            this.ecSubSearchResults = [];
        },

        ecSubFilteredInvoices() {
            if (!this.ecSubClientData) return [];
            let list = [...this.ecSubClientData.invoices];
            if (this.ecSubFilterCurrency !== 'ALL') {
                list = list.filter(i => (i.currency || 'MXN').toUpperCase() === this.ecSubFilterCurrency);
            }
            if (this.ecSubFilterOverdue === 'OVERDUE') {
                list = list.filter(i => i.days_overdue > 0);
            } else if (this.ecSubFilterOverdue === 'CURRENT') {
                list = list.filter(i => i.days_overdue <= 0);
            }
            return list;
        },

        ecSubToggleInvoice(docNum) {
            const idx = this.ecSubSelectedInvoices.indexOf(docNum);
            if (idx >= 0) {
                this.ecSubSelectedInvoices.splice(idx, 1);
            } else {
                this.ecSubSelectedInvoices.push(docNum);
            }
        },

        ecSubToggleAll() {
            const filtered = this.ecSubFilteredInvoices();
            const allSelected = filtered.every(i => this.ecSubSelectedInvoices.includes(i.doc_num));
            if (allSelected) {
                const nums = filtered.map(i => i.doc_num);
                this.ecSubSelectedInvoices = this.ecSubSelectedInvoices.filter(n => !nums.includes(n));
            } else {
                filtered.forEach(i => {
                    if (!this.ecSubSelectedInvoices.includes(i.doc_num)) {
                        this.ecSubSelectedInvoices.push(i.doc_num);
                    }
                });
            }
        },

        ecSubAllSelected() {
            const filtered = this.ecSubFilteredInvoices();
            if (filtered.length === 0) return false;
            return filtered.every(i => this.ecSubSelectedInvoices.includes(i.doc_num));
        },

        ecSubSelectedCount() {
            return this.ecSubSelectedInvoices.length;
        },

        ecSubSelectedTotalMXN() {
            if (!this.ecSubClientData) return 0;
            return this.ecSubClientData.invoices
                .filter(i => this.ecSubSelectedInvoices.includes(i.doc_num) && (i.currency || 'MXN').toUpperCase() !== 'USD')
                .reduce((s, i) => s + i.balance, 0);
        },

        ecSubSelectedTotalUSD() {
            if (!this.ecSubClientData) return 0;
            return this.ecSubClientData.invoices
                .filter(i => this.ecSubSelectedInvoices.includes(i.doc_num) && (i.currency || 'MXN').toUpperCase() === 'USD')
                .reduce((s, i) => s + i.balance, 0);
        },

        ecSubGenerateBill() {
            if (this.ecSubSelectedCount() === 0) return;
            const cardCode = this.ecSubSelectedClient.card_code;
            const invoices = this.ecSubSelectedInvoices.join(',');
            const url = `/orders/estado-cuenta?card_code=${cardCode}&invoices=${invoices}`;
            window.open(url, '_blank');
        },

        pushUndo(action) {
            this.undoStack.push(action);
            if (this.undoStack.length > 50) this.undoStack.shift();
        },

        async toggleSignature(area) {
            if (!this.currentRelacion || !this.currentRelacion.folio) return;
            const isSigned = !!this.signatures[area];
            const action = isSigned ? 'unsign' : 'sign';

            // Check client-side permissions before calling API
            if (action === 'sign') {
                const canSign = {
                    facturacion: this.canSignFacturacion,
                    credito: this.canSignCredito,
                };
                if (!canSign[area]) {
                    const labels = {
                        facturacion: 'Facturación',
                        credito: 'Crédito y Cobranza',
                    };
                    alert(`Solo el jefe de ${labels[area]} puede firmar esta área.`);
                    return;
                }
            }

            try {
                const res = await fetch(`/orders/api/relaciones/${this.currentRelacion.folio}/signatures`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ area, action }),
                });
                const data = await res.json();
                if (data.success && data.signatures) {
                    this.signatures = {
                        facturacion: data.signatures.facturacion || null,
                        credito: data.signatures.credito || null,
                    };
                } else {
                    alert(data.error || 'Error al actualizar firma');
                }
            } catch (e) {
                console.error('Error toggling signature:', e);
                // Optimistic fallback
                if (isSigned) {
                    this.signatures[area] = null;
                } else {
                    this.signatures[area] = { 
                        name: this.currentUserFullName,
                        signature_path: this.currentUserSignature
                    };
                }
            }
        },

        async undo() {
            if (this.undoStack.length === 0) return;
            const action = this.undoStack.pop();
            
            if (action.type === 'drag') {
                this.manualOrder = action.oldOrder;
                this.sortColumn = action.oldSortColumn;
                this.saveManualOrder();
                
                if (action.categoryChange) {
                    await this.updateCategory(action.categoryChange.invoiceNum, action.categoryChange.oldCategory, true);
                } else {
                    this.invoices = [...this.invoices];
                }
            } else if (action.type === 'category_change') {
                await this.updateCategory(action.invoiceNum, action.oldCategory, true);
            }
        },



        handleGlobalKeydown(e) {
            const tag = e.target.tagName;
            const isTextInput = tag === 'TEXTAREA' || 
                                (tag === 'INPUT' && !['checkbox', 'radio'].includes(e.target.type)) || 
                                tag === 'SELECT';
            
            if (isTextInput) return;

            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
                e.preventDefault();
                this.undo();
                return;
            }

            if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                const selectedInvoices = this.invoices.filter(i => i._selected);
                if (selectedInvoices.length > 0) {
                    e.preventDefault();
                    const offset = e.key === 'ArrowUp' ? -1 : 1;
                    
                    // Sort selected by current position so we move them in the right order
                    selectedInvoices.sort((a, b) => {
                        return offset === -1 ? a._global_index - b._global_index : b._global_index - a._global_index;
                    });

                    const previousOrder = [...this.manualOrder];
                    const previousSortColumn = this.sortColumn;

                    // Wrap ALL moves in a SINGLE animateReorder to avoid overlapping FLIP animations
                    const movedInvNum = selectedInvoices.length === 1 ? String(selectedInvoices[0].invoice_number) : null;
                    this.animateReorder(() => {
                        selectedInvoices.forEach(inv => {
                            // Perform raw swap without animation (animateReorder wraps the whole batch)
                            this._rawOrderSwap(inv, offset);
                        });
                        this.saveManualOrder();
                        this.invoices = [...this.invoices];
                    }, movedInvNum);

                    // Highlight only the moved row(s) AFTER animation starts
                    setTimeout(() => {
                        selectedInvoices.forEach(inv => {
                            this.highlightInvoice(String(inv.invoice_number));
                        });
                    }, 100);

                    this.pushUndo({
                        type: 'drag',
                        oldOrder: previousOrder,
                        oldSortColumn: previousSortColumn,
                        categoryChange: null
                    });
                }
            }
        },

        async setColor(invoiceNum, color) {
            const currentSelectedColor = this.rowColors[invoiceNum] || '';
            const targetColor = (currentSelectedColor === color) ? '' : color;

            const inv = this.invoices.find(i => i.invoice_number === invoiceNum);
            const targets = [];
            if (inv && inv._selected) {
                this.invoices.forEach(i => {
                    if (i._selected) {
                        targets.push(i.invoice_number);
                    }
                });
            } else {
                targets.push(invoiceNum);
            }

            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
            for (let id of targets) {
                this.rowColors[id] = targetColor;
                try {
                    await fetch(`/orders/api/facturas/${id}/color`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                        body: JSON.stringify({ color: targetColor, client_id: this.clientId })
                    });
                } catch(e) { console.error('Error saving color:', e); }
            }
        },

        getBaseColorClass(color) {
            if (!color) return 'bg-white border-slate-300';
            return 'btn-color-' + color;
        },

        getColorClass(invoiceNum, isButton = false) {
            const color = this.rowColors[invoiceNum];
            if (!color) return isButton ? 'bg-white border-slate-300' : 'bg-white';
            return isButton ? 'btn-color-' + color : 'row-color-' + color;
        },

        saveColors() {},
        loadColors() {},

        async addExtraInvoice() {
            // Legacy fallback — now handled by the modal
            this.showAddInvoiceModal();
        },

        // ══════════════════════════════════════════════════════
        // Add Invoice Modal Methods
        // ══════════════════════════════════════════════════════

        async showAddInvoiceModal() {
            this.addInvoiceModalOpen = true;
            this.addInvoiceSearchQuery = '';
            this.addInvoiceSelectedPending = [];
            this.addInvoiceManualNum = '';
            this.addInvoiceManualList = [];
            this.addInvoiceOtherDaysPending = [];
            
            // Fetch pending invoices from other days
            this.addInvoiceLoading = true;
            try {
                const res = await fetch(`${cfg.apiFacturasPendingSummaryUrl}?_=${Date.now()}`, { cache: 'no-store' });
                const data = await res.json();
                if (res.ok && data.days) {
                    const dayNames = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
                    const monthNames = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
                    
                    // Get current-day invoice numbers to exclude duplicates
                    const currentDayNums = new Set(this.invoices.map(i => i.invoice_number));
                    
                    this.addInvoiceOtherDaysPending = data.days
                        .filter(day => day.date !== this.selectedDate && day.invoices && day.invoices.length > 0)
                        .map(day => {
                            let label = day.date;
                            try {
                                const [y, m, d] = day.date.split('-').map(Number);
                                const dateObj = new Date(y, m - 1, d);
                                label = dayNames[dateObj.getDay()] + ' ' + d + ' ' + monthNames[m - 1] + ' ' + y;
                            } catch(_) {}
                            return {
                                date: day.date,
                                label: label,
                                invoices: day.invoices.filter(inv => !currentDayNums.has(inv.invoice_number))
                            };
                        })
                        .filter(day => day.invoices.length > 0);
                }
            } catch (e) {
                console.error('Error fetching pending summary for modal:', e);
            } finally {
                this.addInvoiceLoading = false;
            }
        },

        closeAddInvoiceModal() {
            this.addInvoiceModalOpen = false;
            this.addInvoiceSearchQuery = '';
            this.addInvoiceSelectedPending = [];
            this.addInvoiceManualNum = '';
            this.addInvoiceManualList = [];
            this.addInvoiceOtherDaysPending = [];
        },

        /**
         * Returns list of pending invoices for the CURRENT date
         * (invoices not yet selected for Relación and not cancelled).
         */
        get addInvoicePendingList() {
            return this.invoices.filter(i => 
                !i._selected && 
                i.status !== 'Cancelada'
            );
        },

        /**
         * Returns all other-day pending invoices as a flat array
         */
        get addInvoiceOtherDaysFlat() {
            const result = [];
            for (const day of this.addInvoiceOtherDaysPending) {
                for (const inv of day.invoices) {
                    result.push({ ...inv, _fromDate: day.date, _fromLabel: day.label });
                }
            }
            return result;
        },

        /**
         * Combined: current-day + other-days, for total count
         */
        get addInvoiceAllPendingCombined() {
            const current = this.addInvoicePendingList.map(i => ({ ...i, _fromDate: this.selectedDate, _fromLabel: 'Hoy' }));
            return [...current, ...this.addInvoiceOtherDaysFlat];
        },

        get addInvoiceFilteredPendingList() {
            const q = (this.addInvoiceSearchQuery || '').trim().toLowerCase();
            if (!q) return this.addInvoicePendingList;
            return this.addInvoicePendingList.filter(inv => 
                String(inv.invoice_number).includes(q) ||
                (inv.customer_name || '').toLowerCase().includes(q)
            );
        },

        get addInvoiceFilteredOtherDays() {
            const q = (this.addInvoiceSearchQuery || '').trim().toLowerCase();
            if (!q) return this.addInvoiceOtherDaysPending;
            return this.addInvoiceOtherDaysPending
                .map(day => ({
                    ...day,
                    invoices: day.invoices.filter(inv =>
                        String(inv.invoice_number).includes(q) ||
                        (inv.customer_name || '').toLowerCase().includes(q)
                    )
                }))
                .filter(day => day.invoices.length > 0);
        },

        get addInvoiceAllPendingSelected() {
            const filtered = this.addInvoiceFilteredPendingList;
            const otherFiltered = this.addInvoiceFilteredOtherDays.flatMap(d => d.invoices);
            const allFiltered = [...filtered, ...otherFiltered];
            return allFiltered.length > 0 && allFiltered.every(inv => 
                this.addInvoiceSelectedPending.includes(inv.invoice_number)
            );
        },

        get addInvoiceTotalSelected() {
            return this.addInvoiceSelectedPending.length + this.addInvoiceManualList.length;
        },

        togglePendingForAdd(invoiceNum) {
            const idx = this.addInvoiceSelectedPending.indexOf(invoiceNum);
            if (idx >= 0) {
                this.addInvoiceSelectedPending.splice(idx, 1);
            } else {
                this.addInvoiceSelectedPending.push(invoiceNum);
            }
        },

        toggleAllPendingForAdd() {
            const filtered = this.addInvoiceFilteredPendingList;
            const otherFiltered = this.addInvoiceFilteredOtherDays.flatMap(d => d.invoices);
            const allFiltered = [...filtered, ...otherFiltered];
            const filteredNums = allFiltered.map(i => i.invoice_number);
            const allSelected = filteredNums.every(n => this.addInvoiceSelectedPending.includes(n));
            if (allSelected) {
                this.addInvoiceSelectedPending = this.addInvoiceSelectedPending.filter(
                    n => !filteredNums.includes(n)
                );
            } else {
                const newSet = new Set([...this.addInvoiceSelectedPending, ...filteredNums]);
                this.addInvoiceSelectedPending = [...newSet];
            }
        },

        addManualInvoiceToList() {
            const raw = (this.addInvoiceManualNum || '').trim();
            if (!raw || isNaN(raw)) return;
            const numInt = parseInt(raw, 10);
            
            // Check if already in the invoices list
            if (this.invoices.some(i => i.invoice_number === numInt)) {
                alert('Esa factura ya está en la lista del día.');
                return;
            }
            // Check if already in manual list
            if (this.addInvoiceManualList.includes(numInt)) {
                alert('Esa factura ya fue agregada.');
                return;
            }
            // Check if already in extra invoices
            if (this.extraInvoices.includes(numInt)) {
                alert('Esa factura ya está en las facturas extras.');
                return;
            }
            
            this.addInvoiceManualList.push(numInt);
            this.addInvoiceManualNum = '';
        },

        removeManualInvoiceFromList(num) {
            this.addInvoiceManualList = this.addInvoiceManualList.filter(n => n !== num);
        },

        async addSelectedInvoices() {
            if (this.addInvoiceTotalSelected === 0) return;

            let added = 0;
            
            // Collect invoice numbers from other-days pending that were selected
            const currentDayNums = new Set(this.invoices.map(i => i.invoice_number));
            const otherDaySelected = this.addInvoiceSelectedPending.filter(n => !currentDayNums.has(n));

            // 1. Add manually entered invoices to extraInvoices
            for (const numInt of this.addInvoiceManualList) {
                if (!this.extraInvoices.includes(numInt)) {
                    this.extraInvoices.push(numInt);
                    added++;
                }
            }

            // 2. Add other-day pending invoices as extra invoices too
            for (const numInt of otherDaySelected) {
                if (!this.extraInvoices.includes(numInt)) {
                    this.extraInvoices.push(numInt);
                    added++;
                }
            }

            // 3. Save extras if we added any invoices
            if (added > 0) {
                await this.saveExtraInvoices();
            }

            // Close the modal
            this.closeAddInvoiceModal();

            // Refresh to pick up any new invoices from SAP
            if (added > 0) {
                this.fetchInvoices();
            }
        },

        // ══════════════════════════════════════════════════════

        async saveExtraInvoices() {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                await fetch('/orders/api/facturas/extra', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ date: this.selectedDate, extra_invoices: this.extraInvoices, client_id: this.clientId })
                });
            } catch(e) { console.error('Error saving extra invoices:', e); }
        },

        loadExtraInvoices() {},

        getDisplayCustomerName(inv) {
            if (this.customCustomerNames && this.customCustomerNames[inv.invoice_number]) {
                return this.customCustomerNames[inv.invoice_number];
            }
            return inv.customer_name;
        },

        editCustomerName(inv) {
            inv._temp_customer = this.getDisplayCustomerName(inv);
            if ((inv._temp_customer || '').includes('VENTAS MOSTRADOR')) {
                inv._temp_customer = '';
            }
            inv._editing_customer = true;
        },

        async saveCustomerName(inv) {
            if (inv._editing_customer) {
                const newName = inv._temp_customer.trim();
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                if (newName && !newName.includes('VENTAS MOSTRADOR')) {
                    this.customCustomerNames[inv.invoice_number] = newName;
                } else {
                    delete this.customCustomerNames[inv.invoice_number];
                }
                inv._editing_customer = false;
                try {
                    await fetch(`/orders/api/facturas/${inv.invoice_number}/customer-name`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                        body: JSON.stringify({ customer_name: newName, client_id: this.clientId })
                    });
                    this.triggerAutoSaveRelacion();
                } catch(e) { console.error('Error saving customer name:', e); }
            }
        },

        saveCustomNames() {},
        loadCustomNames() {},

        // Invoices filtered only by status (used for shipping counts)
        get filteredByStatusInvoices() {
            let result = this.invoices;
            if (this.statusFilter) {
                result = result.filter(i => i.status === this.statusFilter);
            }
            return result;
        },

        init() {
            // Register Alpine store for tab visibility (permissions-driven)
            const tabsCfg = (window.__facturasConfig || {}).tabs || {
                facturas: true, credito: true, relaciones: true, pendientes: true, almacen: true
            };
            if (window.Alpine && Alpine.store) {
                Alpine.store('tabs', tabsCfg);
            } else {
                document.addEventListener('alpine:init', () => Alpine.store('tabs', tabsCfg));
            }

            window.addEventListener('storage', (e) => {
                if (e.key === 'qb_facturas_sort_state') {
                    try {
                        const state = JSON.parse(e.newValue);
                        if (state && state.date === this.selectedDate) {
                            this.animateReorder(() => {
                                this.sortColumn = state.sortColumn;
                                this.sortDir = state.sortDir;
                            });
                        }
                    } catch (err) {}
                }
            });

            this.selectedDate = new Date().toISOString().split('T')[0];
        },

        get dateLabel() {
            const today = new Date().toISOString().split('T')[0];
            if (this.selectedDate === today) {
                return 'Hoy — ' + new Date().toLocaleDateString('es-MX', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
            }
            const d = new Date(this.selectedDate + 'T12:00:00');
            return d.toLocaleDateString('es-MX', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        },

        get filteredInvoices() {
            let result = this.invoices;

            if (this.statusFilter) {
                result = result.filter(i => i.status === this.statusFilter);
            }

            return this.sortInvoicesArray(result);
        },

        get creditoTabInvoices() {
            let result = this.invoices.filter(i => i.status !== 'Cancelada');
            return this.sortInvoicesArray(result);
        },

        get creditoTabFilteredInvoices() {
            let result = this.creditoTabInvoices;
            if (this.creditoSubTab === 'Crédito') {
                result = result.filter(i => this.isCredito(i));
            } else if (this.creditoSubTab === 'Contado') {
                result = result.filter(i => this.isContado(i));
            }
            if (this.searchQuery && this.searchQuery.trim() !== '') {
                result = result.filter(i => this.isMatch(i));
            }
            return result;
        },

        get pendingInvoices() {
            return this.invoices.filter(i => !i._selected && i.status !== 'Cancelada');
        },

        get pendingInvoicesByDate() {
            const groups = {};
            const dayNames = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
            const monthNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

            this.pendingInvoices.forEach(inv => {
                // Normalize: take only the YYYY-MM-DD portion
                const raw = String(inv.invoice_date || '').trim();
                const dateKey = raw.length >= 10 ? raw.substring(0, 10) : (raw || 'Sin Fecha');

                if (!groups[dateKey]) {
                    let label = dateKey;
                    if (dateKey !== 'Sin Fecha' && dateKey.includes('-')) {
                        try {
                            const [year, month, day] = dateKey.split('-').map(Number);
                            if (!isNaN(year) && !isNaN(month) && !isNaN(day)) {
                                const d = new Date(year, month - 1, day);
                                label = dayNames[d.getDay()] + ', ' + day + ' de ' + monthNames[month - 1] + ' de ' + year;
                            }
                        } catch(e) { /* keep raw key */ }
                    }
                    groups[dateKey] = { dateKey, label, invoices: [], total: 0 };
                }
                groups[dateKey].invoices.push(inv);
                groups[dateKey].total += Number(inv.total || 0);
            });

            return Object.values(groups).sort((a, b) => b.dateKey.localeCompare(a.dateKey));
        },


        sortInvoicesArray(arr) {
            const col = this.sortColumn;
            
            if (col === 'manual' && this.manualOrder.length > 0) {
                return [...arr].sort((a, b) => {
                    const idxA = this.manualOrder.indexOf(String(a.invoice_number));
                    const idxB = this.manualOrder.indexOf(String(b.invoice_number));
                    if (idxA === -1 && idxB === -1) return 0;
                    if (idxA === -1) return 1;
                    if (idxB === -1) return -1;
                    return idxA - idxB;
                });
            }

            const dir = this.sortDir === 'asc' ? 1 : -1;
            return [...arr].sort((a, b) => {
                let av = a[col];
                let bv = b[col];
                
                // Special case for shipping type default
                if (col === 'shipping_type') {
                    av = av || 'LOCAL';
                    bv = bv || 'LOCAL';
                }
                
                // Fallbacks for other cols
                av = av ?? 0;
                bv = bv ?? 0;

                if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
                return String(av).localeCompare(String(bv)) * dir;
            });
        },

        formatWarehouse(whCode) {
            const wh = String(whCode || '').trim();
            if (wh === '01') return 'GDL';
            if (wh === '03') return 'Monterrey';
            if (wh === '04') return 'Irapuato';
            return wh || 'Sin Almacén';
        },

        get allSelected() {
            const authorizable = this.invoices.filter(i => this.canBeInRelation(i));
            return authorizable.length > 0 && authorizable.every(i => i._selected);
        },

        canBeInRelation(inv) {
            return inv.credito_authorized || inv.status === 'Cancelada';
        },

        toggleAll() {
            const state = !this.allSelected;
            const authorizable = this.invoices.filter(i => this.canBeInRelation(i));
            authorizable.forEach(i => i._selected = state);
            
            // Sync to local storage
            const selected = this.invoices.filter(i => i._selected).map(i => String(i.invoice_number));
            localStorage.setItem('qb_facturas_selected_' + this.selectedDate, JSON.stringify(selected));
            
            // Send bulk toggle to server
            this.toggleInvoiceSelection(authorizable, state);
        },

        saveSelection() {
            this.$nextTick(() => {
                const selected = this.invoices.filter(i => i._selected).map(i => String(i.invoice_number));
                localStorage.setItem('qb_facturas_selected_' + this.selectedDate, JSON.stringify(selected));
            });
        },

        lastCheckedIndex: null,

        handleCheck(evt, inv) {
            if (!this.canBeInRelation(inv)) {
                evt.preventDefault();
                alert('No puedes agregar esta factura a la relación porque no ha sido autorizada por Crédito y Cobranza.');
                return;
            }
            const targetState = evt.target.checked;
            let toggledInvoices = [inv];
            if (evt.shiftKey && this.lastCheckedIndex !== null) {
                const start = Math.min(this.lastCheckedIndex, inv._global_index);
                const end = Math.max(this.lastCheckedIndex, inv._global_index);
                
                toggledInvoices = [];
                this.invoices.forEach(i => {
                    if (i._global_index && i._global_index >= start && i._global_index <= end && this.canBeInRelation(i)) {
                        i._selected = targetState;
                        toggledInvoices.push(i);
                    }
                });
                window.getSelection().removeAllRanges();
            } else {
                inv._selected = targetState;
            }
            this.lastCheckedIndex = inv._global_index;
            
            this.saveSelection();
            this.toggleInvoiceSelection(toggledInvoices, targetState);
        },

        handleRowClick(evt, inv) {
            if (['INPUT', 'BUTTON', 'A', 'TEXTAREA', 'SELECT', 'SVG', 'path'].includes(evt.target.tagName)) return;
            if (evt.target.closest('.drag-handle')) return;
            if (!this.canBeInRelation(inv)) return;
            
            if (evt.ctrlKey || evt.metaKey) {
                inv._selected = !inv._selected;
                this.lastCheckedIndex = inv._global_index;
                window.getSelection().removeAllRanges();
                this.saveSelection();
                this.toggleInvoiceSelection(inv, inv._selected);
            } else if (evt.shiftKey && this.lastCheckedIndex !== null) {
                const start = Math.min(this.lastCheckedIndex, inv._global_index);
                const end = Math.max(this.lastCheckedIndex, inv._global_index);
                const targetState = true;
                
                const toggled = [];
                this.invoices.forEach(i => {
                    if (i._global_index && i._global_index >= start && i._global_index <= end && this.canBeInRelation(i)) {
                        i._selected = targetState;
                        toggled.push(i);
                    }
                });
                this.lastCheckedIndex = inv._global_index;
                window.getSelection().removeAllRanges();
                this.saveSelection();
                if (toggled.length > 0) this.toggleInvoiceSelection(toggled, targetState);
            }
        },

        get invoiceGroups() {
            const groups = {};
            const categoryOrder = [
                'LOCAL', 'ENVIO LOCAL', 'VENTA MOSTRADOR', 'PAQUETERIA', 'PASE A PAQUETERIA', 
                'PASE DIRECTO', 'PASE PROGRAMADO', 'FLETE INTERNO', 'FORANEO', 
                'ANEXADAS MTY', 'ANEXADAS GDL', 'ANEXADAS IRP'
            ];

            this.filteredInvoices.forEach(i => {
                let s = (i.shipping_type || 'LOCAL').toUpperCase();
                if (s === 'ANEXO MTY') s = 'ANEXADAS MTY';
                if (s === 'ANEXO GDL') s = 'ANEXADAS GDL';
                if (s === 'ANEXO IRP') s = 'ANEXADAS IRP';
                const category = s;

                if (!groups[category]) {
                    groups[category] = {
                        category: category,
                        invoices: []
                    };
                }
                groups[category].invoices.push(i);
            });

            let globalIndex = 1;
            return Object.values(groups).sort((a, b) => {
                const ai = categoryOrder.indexOf(a.category);
                const bi = categoryOrder.indexOf(b.category);
                const aIdx = ai >= 0 ? ai : 100;
                const bIdx = bi >= 0 ? bi : 100;
                if (aIdx !== bIdx) return aIdx - bIdx;
                return a.category.localeCompare(b.category);
            }).map(g => {
                g.invoices.forEach(inv => {
                    inv._global_index = globalIndex++;
                });
                return {
                    name: g.category,
                    category: g.category,
                    invoices: g.invoices
                };
            });
        },

        get relacionInvoiceGroups() {
            // Explicitly track reactive dependencies for Alpine.js
            const _trackSortCol = this.sortColumn;
            const _trackSortDir = this.sortDir;
            const _trackManual = this.manualOrder;

            if (!this.currentRelacion || !this.currentRelacion.invoices) return [];
            const groups = {};
            const categoryOrder = [
                'LOCAL', 'ENVIO LOCAL', 'VENTA MOSTRADOR', 'PAQUETERIA', 'PASE A PAQUETERIA', 
                'PASE DIRECTO', 'PASE PROGRAMADO', 'FLETE INTERNO', 'FORANEO', 
                'ANEXADAS MTY', 'ANEXADAS GDL', 'ANEXADAS IRP'
            ];

            const invoicesMap = new Map();
            this.invoices.forEach(i => invoicesMap.set(String(i.invoice_number), i));

            this.currentRelacion.invoices.forEach(inv => {
                const liveInv = invoicesMap.get(String(inv.invoice_number));
                const resolvedInv = liveInv ? { ...inv, ...liveInv } : inv;

                let cat = (resolvedInv.shipping_type || resolvedInv.observaciones || resolvedInv.nota || 'LOCAL').toUpperCase();
                if (cat === 'ANEXO MTY') cat = 'ANEXADAS MTY';
                if (cat === 'ANEXO GDL') cat = 'ANEXADAS GDL';
                if (cat === 'ANEXO IRP') cat = 'ANEXADAS IRP';

                if (!groups[cat]) {
                    groups[cat] = { category: cat, invoices: [] };
                }
                groups[cat].invoices.push(resolvedInv);
            });

            const invoiceIndexMap = new Map();
            this.sortInvoicesArray(this.invoices).forEach((inv, idx) => {
                invoiceIndexMap.set(String(inv.invoice_number), idx);
            });

            return Object.values(groups).sort((a, b) => {
                const ai = categoryOrder.indexOf(a.category);
                const bi = categoryOrder.indexOf(b.category);
                const aIdx = ai >= 0 ? ai : 100;
                const bIdx = bi >= 0 ? bi : 100;
                if (aIdx !== bIdx) return aIdx - bIdx;
                return a.category.localeCompare(b.category);
            }).map(g => {
                g.invoices.sort((a, b) => {
                    const idxA = invoiceIndexMap.has(String(a.invoice_number)) ? invoiceIndexMap.get(String(a.invoice_number)) : 999999;
                    const idxB = invoiceIndexMap.has(String(b.invoice_number)) ? invoiceIndexMap.get(String(b.invoice_number)) : 999999;
                    return idxA - idxB;
                });
                return g;
            });
        },

        isMatch(i) {
            if (!this.searchQuery || this.searchQuery.trim() === '') return false;
            const q = this.searchQuery.toLowerCase().trim();
            const custName = this.getDisplayCustomerName(i) || '';
            return String(i.invoice_number).includes(q) ||
                   custName.toLowerCase().includes(q) ||
                   (i.customer_code && i.customer_code.toLowerCase().includes(q)) ||
                   (i.seller_name && i.seller_name.toLowerCase().includes(q)) ||
                   (i.order_number && String(i.order_number).toLowerCase().includes(q));
        },

        escapeHTML(str) {
            return String(str)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        },
        
        highlightText(text) {
            if (text == null) return '';
            const str = String(text);
            const escaped = this.escapeHTML(str);
            if (!this.searchQuery || this.searchQuery.trim() === '') return escaped;
            
            const q = this.searchQuery.trim();
            const regexSafeQuery = this.escapeHTML(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${regexSafeQuery})`, 'gi');
            return escaped.replace(regex, '<mark class="bg-amber-400 text-amber-900 px-1 py-0.5 rounded shadow-sm">$1</mark>');
        },

        scrollToFirstMatch() {
            const el = document.querySelector('.match-row');
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        },

        init() {
            this.fetchInvoices();
            // Load saved views
            try {
                const saved = localStorage.getItem('qb_facturas_saved_views');
                if (saved) this.savedViews = JSON.parse(saved);
            } catch(e) { console.warn(e); }

            this.$watch('searchQuery', (value) => {
                if (value && value.trim() !== '') {
                    this.$nextTick(() => {
                        this.scrollToFirstMatch();
                    });
                }
            });

            this.$watch('selectedDate', (value) => {
                if (value) {
                    localStorage.setItem('qb_facturas_date', value);
                    this.fetchInvoices();
                }
            });

            this.$watch('activeTab', (value) => {
                localStorage.setItem('qb_facturas_active_tab', value);
                if (value === 'relaciones') {
                    this.fetchRelaciones();
                }
            });

            if (this.activeTab === 'relaciones') {
                this.fetchRelaciones();
            }

            // Listen to global SSE events broadcasted by base.html
            window.addEventListener('sse-message', (e) => {
                this.handleSSEEvent(e.detail);
            });
        },

        animateReorder(callback, movedId = null) {
            const rows = Array.from(document.querySelectorAll('#facturas-table tbody tr[data-id], #relaciones-table tbody tr[data-id]'));
            const firstPositions = new Map();
            
            rows.forEach(row => {
                const isFact = !!row.closest('#facturas-table');
                const key = (isFact ? 'fact-' : 'rel-') + row.getAttribute('data-id');
                const rect = row.getBoundingClientRect();
                firstPositions.set(key, {
                    top: rect.top,
                    left: rect.left
                });
            });

            callback();

            this.$nextTick(() => {
                const nextRows = Array.from(document.querySelectorAll('#facturas-table tbody tr[data-id], #relaciones-table tbody tr[data-id]'));
                
                // Group by table
                const factRows = [];
                const relRows = [];
                nextRows.forEach(row => {
                    if (row.closest('#facturas-table')) {
                        factRows.push(row);
                    } else {
                        relRows.push(row);
                    }
                });

                const processGroup = (groupRows, prefix) => {
                    const movedRows = [];
                    groupRows.forEach(row => {
                        const key = prefix + row.getAttribute('data-id');
                        if (firstPositions.has(key)) {
                            const firstPos = firstPositions.get(key);
                            const lastRect = row.getBoundingClientRect();
                            const dy = firstPos.top - lastRect.top;
                            const dx = firstPos.left - lastRect.left;
                            if (dy !== 0 || dx !== 0) {
                                movedRows.push({ row, dx, dy, absDy: Math.abs(dy), id: row.getAttribute('data-id') });
                            }
                        }
                    });

                    if (movedRows.length === 0) return;

                    // Find the climbing row:
                    // 1. If movedId matches one of the moved rows in this group, use it.
                    // 2. Otherwise, fallback to the row with the maximum absolute vertical displacement.
                    let climbingItem = null;
                    if (movedId) {
                        const matchId = String(movedId);
                        climbingItem = movedRows.find(item => String(item.id) === matchId);
                    }
                    
                    if (!climbingItem) {
                        let maxAbsDy = -1;
                        movedRows.forEach(item => {
                            if (item.absDy > maxAbsDy) {
                                maxAbsDy = item.absDy;
                                climbingItem = item;
                            }
                        });
                    }

                    // Initial state (no transitions, positioned at start of FLIP)
                    // Note: climbing row starts at scale(1.00) and no shadow to avoid initial visual jump.
                    movedRows.forEach(item => {
                        const r = item.row;
                        r.style.setProperty('transition', 'none', 'important');
                        
                        if (item === climbingItem) {
                            r.style.position = 'relative';
                            r.style.zIndex = '99';
                            r.style.boxShadow = 'none';
                            r.style.transform = `translate(${item.dx}px, ${item.dy}px) scale(1.00)`;
                        } else {
                            r.style.transform = `translate(${item.dx}px, ${item.dy}px)`;
                        }
                        
                        r.offsetHeight; // force reflow
                    });

                    // Phase 1: Transition to destination with elevation (scale and shadow)
                    setTimeout(() => {
                        movedRows.forEach(item => {
                            const r = item.row;
                            r.style.removeProperty('transition');
                            if (item === climbingItem) {
                                r.style.boxShadow = '0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.15)';
                                r.style.transform = 'translate(0px, 0px) scale(1.03)';
                            } else {
                                r.style.transform = '';
                            }
                        });

                        // Phase 2: Land (scale down and fade shadow) when translation is complete (600ms)
                        setTimeout(() => {
                            if (climbingItem) {
                                const r = climbingItem.row;
                                r.style.setProperty('transition', 'transform 150ms ease, box-shadow 150ms ease', 'important');
                                r.style.transform = 'scale(1.00)';
                                r.style.boxShadow = 'none';
                                
                                // Final cleanup after landing finishes (150ms)
                                setTimeout(() => {
                                    r.style.position = '';
                                    r.style.zIndex = '';
                                    r.style.boxShadow = '';
                                    r.style.transform = '';
                                    r.style.removeProperty('transition');
                                }, 150);
                            }
                        }, 600);
                    }, 50);
                };

                processGroup(factRows, 'fact-');
                processGroup(relRows, 'rel-');
            });
        },

        findMovedElement(oldOrder, newOrder) {
            if (!oldOrder || !newOrder) return null;
            if (oldOrder.length !== newOrder.length) return null;
            const setA = new Set(oldOrder);
            for (let x of newOrder) {
                if (!setA.has(x)) return null;
            }
            const common = oldOrder;
            if (common.length <= 1) return null;
            for (let i = 0; i < common.length; i++) {
                const candidate = common[i];
                const oldWithout = oldOrder.filter(x => x !== candidate);
                const newWithout = newOrder.filter(x => x !== candidate);
                let equal = true;
                for (let j = 0; j < oldWithout.length; j++) {
                    if (oldWithout[j] !== newWithout[j]) {
                        equal = false;
                        break;
                    }
                }
                if (equal) return candidate;
            }
            return null;
        },

        highlightInvoice(invoiceNum) {
            const inv = this.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
            if (inv) {
                inv._highlighted = true;
                this.invoices = [...this.invoices];
                setTimeout(() => {
                    inv._highlighted = false;
                    this.invoices = [...this.invoices];
                }, 5000);
            }
        },

        async handleSSEEvent(data) {
            if (!data || !data.type) return;

            if (data.type === 'factura_category_changed') {
                if (data.client_id !== this.clientId) {
                    const inv = this.invoices.find(i => i.invoice_number === data.invoice_number);
                    if (inv) {
                        inv.shipping_type = data.category;
                        this.invoices = [...this.invoices];
                        this.highlightInvoice(data.invoice_number);
                    }
                }
            } else if (data.type === 'factura_credito_changed') {
                const inv = this.invoices.find(i => String(i.invoice_number) === String(data.invoice_number));
                if (inv) {
                    inv.credito_authorized = data.authorized;
                    inv.credito_revoked_from_relacion = data.revoked_from_relacion || false;
                    this.invoices = [...this.invoices];
                    this.highlightInvoice(data.invoice_number);
                }
            } else if (data.type === 'factura_color_changed') {
                if (data.client_id !== this.clientId) {
                    this.rowColors[data.invoice_number] = data.color;
                    this.rowColors = { ...this.rowColors };
                }
            } else if (data.type === 'factura_customer_name_changed') {
                if (data.client_id !== this.clientId) {
                    if (data.customer_name) {
                        this.customCustomerNames[data.invoice_number] = data.customer_name;
                    } else {
                        delete this.customCustomerNames[data.invoice_number];
                    }
                    this.customCustomerNames = { ...this.customCustomerNames };
                }
            } else if (data.type === 'factura_manual_order_changed') {
                if (data.date === this.selectedDate && data.client_id !== this.clientId) {
                    const oldOrder = this.manualOrder || [];
                    const newOrder = data.manual_order || [];
                    const movedInvoiceNum = this.findMovedElement(oldOrder, newOrder);
                    
                    this.animateReorder(() => {
                        this.manualOrder = newOrder;
                        this.sortColumn = 'manual';
                        this.invoices = [...this.invoices];
                    }, movedInvoiceNum);

                    // Highlight ONLY the moved row (if identified) AFTER animation begins.
                    // If findMovedElement couldn't identify the exact row, skip highlighting —
                    // the FLIP animation already shows the change visually.
                    if (movedInvoiceNum) {
                        setTimeout(() => {
                            this.highlightInvoice(movedInvoiceNum);
                        }, 100);
                    }
                }
            } else if (data.type === 'factura_extras_changed') {
                if (data.date === this.selectedDate && data.client_id !== this.clientId) {
                    this.extraInvoices = data.extra_invoices;
                    this.fetchInvoices();
                }
            } else if (data.type === 'order_updated' && data.order) {
                if (data.client_id !== this.clientId) {
                    const updatedOrder = data.order;
                    const inv = this.invoices.find(i => String(i.invoice_number) === String(updatedOrder.factura_number) || String(i.related_order_id) === String(data.order_id));
                    if (inv) {
                        const statusVal = updatedOrder.status;
                        inv.recibido = statusVal === 'Listo' || statusVal === 'Entregado';
                        inv.entrega = statusVal === 'Entregado';
                        inv.observaciones = updatedOrder.observaciones || '';
                        this.invoices = [...this.invoices];
                        this.highlightInvoice(inv.invoice_number);
                    }
                }
            } else if (data.type === 'relacion_updated') {
                if (data.date === this.selectedDate && data.client_id !== this.clientId) {
                    await this.fetchRelacionForDate();
                }
            } else if (data.type === 'factura_observaciones_changed') {
                if (data.client_id !== this.clientId) {
                    const inv = this.invoices.find(i => i.invoice_number === data.invoice_number);
                    if (inv) {
                        inv.observaciones = data.observaciones;
                        this.invoices = [...this.invoices];
                    }
                    if (this.pendingSummaryData) {
                        this.pendingSummaryData.forEach(day => {
                            const pInv = day.invoices.find(i => String(i.invoice_number) === String(data.invoice_number));
                            if (pInv) pInv.observaciones = data.observaciones;
                        });
                    }
                }
            } else if (data.type === 'factura_credito_notes_changed') {
                if (data.client_id !== this.clientId) {
                    const inv = this.invoices.find(i => i.invoice_number === data.invoice_number);
                    if (inv) {
                        inv.credito_notes = data.notes;
                        this.invoices = [...this.invoices];
                    }
                }
            } else if (data.type === 'relacion_signature_changed') {
                if (this.currentRelacion && this.currentRelacion.folio === data.folio) {
                    this.currentRelacion.signatures = data.signatures;
                    this.signatures = {
                        facturacion: data.signatures.facturacion || null,
                        credito: data.signatures.credito || null,
                    };
                }
            } else if (data.type === 'dia_cerrado') {
                if (data.date === this.selectedDate) {
                    this.fetchInvoices();
                }
            }
        },

        initGroupSortable(el, category) {
            if (typeof Sortable === 'undefined') return;
            if (!this.canEditFacturas) return;
            
            let nextSibling = null;
            let previousCategory = null;

            Sortable.create(el, {
                group: 'shared',
                animation: 150,
                handle: '.drag-handle',
                filter: '.ignore-elements, template',
                preventOnFilter: false,
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                delay: 100,
                delayOnTouchOnly: true,
                scroll: true,
                bubbleScroll: true,
                scrollSensitivity: 60,
                scrollSpeed: 15,
                // Build a compact drag image from the original row's text
                setData: (dataTransfer, dragEl) => {
                    const tbl = document.createElement('table');
                    tbl.style.cssText = 'position:fixed;top:-9999px;left:-9999px;background:#fff;border:2px solid #f59e0b;border-radius:4px;box-shadow:0 10px 20px rgba(0,0,0,0.15);padding:0;border-collapse:collapse;font-family:inherit;';
                    const tr = document.createElement('tr');
                    
                    // Collect visible text from key cells of the original row
                    const cells = dragEl.querySelectorAll('td');
                    cells.forEach((td, idx) => {
                        // Skip first cell (drag handle + color picker)
                        if (idx === 0) return;
                        const clone = document.createElement('td');
                        clone.style.cssText = 'padding:6px 10px;font-size:12px;white-space:nowrap;border:1px solid #e2e8f0;max-width:160px;overflow:hidden;text-overflow:ellipsis;';
                        // Get text: prefer x-text elements, fallback to cell textContent
                        const xTextEl = td.querySelector('[x-text]');
                        clone.textContent = (xTextEl ? xTextEl.textContent : td.textContent).trim();
                        if (clone.textContent) tr.appendChild(clone);
                    });
                    
                    tbl.appendChild(tr);
                    document.body.appendChild(tbl);
                    dataTransfer.setDragImage(tbl, 40, 15);
                    requestAnimationFrame(() => tbl.remove());
                },
                onStart: (evt) => {
                    nextSibling = evt.item.nextElementSibling;
                    previousCategory = evt.from.getAttribute('data-category');
                },
                onEnd: (evt) => {
                    const invoiceNum = evt.item.getAttribute('data-id');
                    const previousOrder = [...this.manualOrder];
                    const previousSortColumn = this.sortColumn;
                    let catChange = null;
                    
                    const newOrder = Array.from(evt.to.children)
                        .map(tr => tr.getAttribute('data-id'))
                        .filter(Boolean);
                        
                    // Always revert DOM so Alpine can re-render it naturally
                    if (nextSibling) {
                        evt.from.insertBefore(evt.item, nextSibling);
                    } else {
                        evt.from.appendChild(evt.item);
                    }
                    
                    this.animateReorder(() => {
                        if (evt.from !== evt.to) {
                            const newCategory = evt.to.getAttribute('data-category');
                            if (newCategory) {
                                catChange = { invoiceNum, oldCategory: previousCategory, newCategory };
                                this.updateCategory(invoiceNum, newCategory);
                            }
                        }
                        
                        if (newOrder.length > 0) {
                            if (this.sortColumn !== 'manual') {
                                this.manualOrder = this.filteredInvoices.map(i => String(i.invoice_number));
                            }
                            const currentOrderSet = new Set(this.manualOrder);
                            newOrder.forEach(id => currentOrderSet.delete(id));
                            this.manualOrder = [...newOrder, ...Array.from(currentOrderSet)];
                            this.sortColumn = 'manual';
                            this.saveManualOrder();

                            // Trigger Alpine re-render (no highlight here to avoid double spread)
                            this.invoices = [...this.invoices];
                            
                            this.pushUndo({
                                type: 'drag',
                                oldOrder: previousOrder,
                                oldSortColumn: previousSortColumn,
                                categoryChange: catChange
                            });
                        }
                    });

                    // Highlight AFTER animation starts
                    setTimeout(() => {
                        if (typeof this.highlightInvoice === 'function') {
                            this.highlightInvoice(invoiceNum);
                        }
                    }, 100);
                }
            });
        },

        async saveManualOrder() {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                await fetch('/orders/api/facturas/manual-order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ date: this.selectedDate, manual_order: this.manualOrder, client_id: this.clientId })
                });
                // Sync manual_order to the relación on the server WITHOUT
                // touching this.currentRelacion (avoids re-renders mid-animation).
                if (this.currentRelacion && this.currentRelacion.invoices && this.currentRelacion.invoices.length > 0) {
                    this._syncRelacionOrderToServer();
                }
            } catch(e) { console.error('Error saving manual order:', e); }
        },

        /** Server-only sync of manual_order to the relación – no local state mutation. */
        async _syncRelacionOrderToServer() {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                // Flag to suppress highlight when our own relacion_updated SSE arrives
                this._suppressRelacionHighlight = true;
                await fetch('/orders/api/relaciones/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({
                        date: this.selectedDate,
                        selected: false,
                        invoice_numbers: [],
                        invoice_data: [],
                        manual_order: this.manualOrder,
                        client_id: this.clientId
                    })
                });
                // Clear the flag after a delay to cover the SSE round-trip
                setTimeout(() => { this._suppressRelacionHighlight = false; }, 3000);
            } catch (e) {
                this._suppressRelacionHighlight = false;
                console.error('Error syncing relación order:', e);
            }
        },

        loadManualOrder() {},

        async fetchInvoices() {
            if (this.loading) return;
            this.loading = true;
            this.errorMsg = '';

            if (this.lastFetchedDate !== this.selectedDate) {
                this.isInitialized = false;
            }

            try {
                let params = this.selectedDate ? '?date=' + this.selectedDate : '';
                const res = await fetch(cfg.apiFacturasUrl + params + (params ? '&' : '?') + '_=' + Date.now(), { cache: 'no-store' });
                const data = await res.json();

                if (res.ok) {
                    // Load daily configuration fields returned from backend
                    this.manualOrder = data.manual_order || [];
                    this.extraInvoices = data.extra_invoices || [];
                    this.customCustomerNames = data.custom_customer_names || {};
                    this.rowColors = data.row_colors || {};

                    // Default to manual ordering if manual order is saved, else fallback to invoice number
                    if (this.manualOrder.length > 0) {
                        this.sortColumn = 'manual';
                    } else {
                        this.sortColumn = 'invoice_number';
                    }

                    const dateChanged = (this.lastFetchedDate !== this.selectedDate);
                    this.lastFetchedDate = this.selectedDate;

                    let savedSelection = new Set();
                    try {
                        const saved = localStorage.getItem('qb_facturas_selected_' + this.selectedDate);
                        if (saved) savedSelection = new Set(JSON.parse(saved));
                    } catch(e) {}

                    const selectedInvoiceNumbers = (dateChanged || this.invoices.length === 0) ? savedSelection : new Set(
                        this.invoices.filter(i => i._selected).map(i => String(i.invoice_number))
                    );

                    if (dateChanged || this.invoices.length === 0) {
                        this.invoices = (data.invoices || []).map(i => ({ 
                            ...i, 
                            _editing: false, 
                            _temp_observaciones: '',
                            _editing_customer: false,
                            _temp_customer: '',
                            _selected: selectedInvoiceNumbers.has(String(i.invoice_number)),
                            _editing_position: false,
                            _highlighted: false
                        }));
                    } else {
                        // Merge intelligently to avoid UI flicker
                        const existingMap = new Map(this.invoices.map(i => [String(i.invoice_number), i]));
                        const newInvoices = [];
                        
                        (data.invoices || []).forEach(newInv => {
                            const existingInv = existingMap.get(String(newInv.invoice_number));
                            if (existingInv) {
                                let changed = false;
                                if (existingInv.status !== newInv.status || existingInv.shipping_type !== newInv.shipping_type || existingInv.observaciones !== newInv.observaciones) {
                                    changed = true;
                                }
                                // Update existing object properties without destroying the reference
                                Object.assign(existingInv, newInv);
                                existingInv._selected = selectedInvoiceNumbers.has(String(newInv.invoice_number));
                                if (changed) {
                                    existingInv._highlighted = true;
                                    this.invoices = [...this.invoices];
                                    setTimeout(() => {
                                        existingInv._highlighted = false;
                                        this.invoices = [...this.invoices];
                                    }, 5000);
                                }
                                newInvoices.push(existingInv);
                            } else {
                                // Add new object
                                newInvoices.push({
                                    ...newInv,
                                    _editing: false, 
                                    _temp_observaciones: '',
                                    _editing_customer: false,
                                    _temp_customer: '',
                                    _selected: selectedInvoiceNumbers.has(String(newInv.invoice_number)),
                                    _editing_position: false,
                                    _highlighted: true
                                });
                                setTimeout(() => {
                                    const inv = this.invoices.find(i => String(i.invoice_number) === String(newInv.invoice_number));
                                    if (inv) {
                                        inv._highlighted = false;
                                        this.invoices = [...this.invoices];
                                    }
                                }, 5000);
                            }
                        });
                        this.invoices = newInvoices;
                    }
                    this.stats = data.stats || {};
                    // Fire-and-forget: don't block invoice display waiting for relaciones
                    this.fetchRelacionForDate();
                    this.isInitialized = true;
                } else {
                    this.errorMsg = data.error || 'Error desconocido';
                    console.error('API error:', data.error);
                }
            } catch (e) {
                this.errorMsg = 'Error de connection';
                console.error('Fetch error:', e);
            } finally {
                this.loading = false;
                this.timer = 30;
            }
        },

        async fetchPendingSummary() {
            if (this.pendingSummaryLoading) return;
            this.pendingSummaryLoading = true;
            try {
                const res = await fetch(`${cfg.apiFacturasPendingSummaryUrl}?_=${Date.now()}`, { cache: 'no-store' });
                const data = await res.json();
                if (res.ok) {
                    this.pendingSummaryData = data.days || [];
                }
            } catch (e) {
                console.error("Error fetching pending summary:", e);
            } finally {
                this.pendingSummaryLoading = false;
            }
        },

        setPendingSubTab(tab) {
            this.pendingSubTab = tab;
            localStorage.setItem('qb_facturas_pending_subtab', tab);
            if (tab === 'calendar' || tab === 'all') {
                this.fetchPendingSummary();
            }
        },

        prevPendingMonth() {
            if (this.pendingCalendarMonth === 0) {
                this.pendingCalendarMonth = 11;
                this.pendingCalendarYear--;
            } else {
                this.pendingCalendarMonth--;
            }
        },

        nextPendingMonth() {
            if (this.pendingCalendarMonth === 11) {
                this.pendingCalendarMonth = 0;
                this.pendingCalendarYear++;
            } else {
                this.pendingCalendarMonth++;
            }
        },

        getPendingCalendarDays() {
            const year = this.pendingCalendarYear;
            const month = this.pendingCalendarMonth;
            const firstDay = new Date(year, month, 1).getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            
            const days = [];
            // Padding for first week
            for (let i = 0; i < firstDay; i++) {
                days.push(null);
            }
            
            // Map data to days
            const summaryMap = {};
            this.pendingSummaryData.forEach(d => summaryMap[d.date] = d);
            
            for (let i = 1; i <= daysInMonth; i++) {
                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
                const data = summaryMap[dateStr] || { total_invoices: 0, pending: 0 };
                days.push({
                    day: i,
                    dateStr: dateStr,
                    data: data,
                    isToday: dateStr === new Date().toISOString().split('T')[0]
                });
            }
            return days;
        },

        getCalendarWeeks() {
            const days = this.getPendingCalendarDays();
            const weeks = [];
            for (let i = 0; i < days.length; i += 7) {
                const week = days.slice(i, i + 7);
                // Pad last week to 7 cells
                while (week.length < 7) week.push(null);
                weeks.push(week);
            }
            return weeks;
        },

        getHeatColor(pendingCount) {
            // Each level returns: bg (full style string), dayNumStyle, badgeStyle, amountStyle
            if (!pendingCount || pendingCount <= 0) return {
                bg: 'background-color: #ffffff;',
                dayNumStyle: 'font-size: 13px; font-weight: 700; color: #64748b;',
                badgeStyle: '',
                amountStyle: ''
            };
            if (pendingCount <= 3) return {
                bg: 'background-color: #fef9c3;',  // yellow-100
                dayNumStyle: 'font-size: 13px; font-weight: 700; color: #713f12;',
                badgeStyle: 'font-size: 12px; font-weight: 800; color: #92400e;',
                amountStyle: 'font-size: 10px; font-weight: 600; color: #a16207;'
            };
            if (pendingCount <= 8) return {
                bg: 'background-color: #fde68a;',  // amber-200
                dayNumStyle: 'font-size: 13px; font-weight: 700; color: #78350f;',
                badgeStyle: 'font-size: 12px; font-weight: 800; color: #78350f;',
                amountStyle: 'font-size: 10px; font-weight: 600; color: #92400e;'
            };
            if (pendingCount <= 15) return {
                bg: 'background-color: #fca5a5;',  // red-300
                dayNumStyle: 'font-size: 13px; font-weight: 700; color: #450a0a;',
                badgeStyle: 'font-size: 12px; font-weight: 800; color: #450a0a;',
                amountStyle: 'font-size: 10px; font-weight: 600; color: #7f1d1d;'
            };
            if (pendingCount <= 25) return {
                bg: 'background-color: #f472b6;',  // pink-400
                dayNumStyle: 'font-size: 13px; font-weight: 800; color: #4a044e;',
                badgeStyle: 'font-size: 12px; font-weight: 800; color: #4a044e;',
                amountStyle: 'font-size: 10px; font-weight: 600; color: #701a75;'
            };
            if (pendingCount <= 40) return {
                bg: 'background-color: #a855f7;',  // purple-500
                dayNumStyle: 'font-size: 13px; font-weight: 800; color: #ffffff;',
                badgeStyle: 'font-size: 12px; font-weight: 800; color: #f3e8ff;',
                amountStyle: 'font-size: 10px; font-weight: 600; color: #e9d5ff;'
            };
            return {
                bg: 'background-color: #4c1d95;',  // violet-900
                dayNumStyle: 'font-size: 13px; font-weight: 800; color: #ffffff;',
                badgeStyle: 'font-size: 12px; font-weight: 800; color: #ddd6fe;',
                amountStyle: 'font-size: 10px; font-weight: 600; color: #c4b5fd;'
            };
        },

        sortBy(column) {
            this.animateReorder(() => {
                if (this.sortColumn === column) {
                    this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    this.sortColumn = column;
                    this.sortDir = 'desc';
                }
                
                // Broadcast the sorting via localStorage for other tabs
                try {
                    localStorage.setItem('qb_facturas_sort_state', JSON.stringify({
                        date: this.selectedDate,
                        sortColumn: this.sortColumn,
                        sortDir: this.sortDir,
                        timestamp: Date.now()
                    }));
                } catch (err) {}
            });
        },

        formatMoney(val) {
            if (val == null) return '$0.00';
            return '$' + parseFloat(val).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        },
        
        // --- Saved Views Logic ---
        saveCurrentView() {
            const name = prompt("Nombre para esta vista guardada:");
            if (!name) return;
            const view = {
                name: name,
                filters: {
                    searchQuery: this.searchQuery,
                    statusFilter: this.statusFilter,
                    sortColumn: this.sortColumn,
                    sortDir: this.sortDir,
                    selectedDate: this.selectedDate
                }
            };
            this.savedViews.push(view);
            localStorage.setItem('qb_facturas_saved_views', JSON.stringify(this.savedViews));
        },
        
        applyView(view) {
            this.searchQuery = view.filters.searchQuery || '';
            this.statusFilter = view.filters.statusFilter || 'Abierta';
            this.sortColumn = view.filters.sortColumn || 'invoice_number';
            this.sortDir = view.filters.sortDir || 'desc';
            
            if (view.filters.selectedDate && view.filters.selectedDate !== this.selectedDate) {
                this.selectedDate = view.filters.selectedDate;
                this.fetchInvoices();
            }
        },
        
        deleteView(index) {
            this.savedViews.splice(index, 1);
            localStorage.setItem('qb_facturas_saved_views', JSON.stringify(this.savedViews));
        },
        
        // --- Excel Export ---
        async exportToExcel() {
            const dateVal = this.selectedDate;
            if (!dateVal || !/^\d{4}-\d{2}-\d{2}$/.test(dateVal)) {
                alert('Fecha inválida. Seleccione una fecha válida antes de exportar.');
                return;
            }

            const hasSelected = this.invoices.some(i => i._selected);
            const payload = {
                date: dateVal,
                groups: this.invoiceGroups.map(g => ({
                    ...g,
                    invoices: hasSelected ? g.invoices.filter(i => i._selected) : g.invoices
                })).filter(g => g.invoices.length > 0)
            };

            if (payload.groups.length === 0) {
                alert('No hay facturas para exportar en esta vista.');
                return;
            }

            try {
                this.loading = true;
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                const url = cfg.apiFacturasExportUrl;
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    // Backend returned an error (JSON)
                    let errMsg = 'Error al generar el archivo Excel.';
                    try {
                        const errData = await res.json();
                        errMsg = errData.error || errMsg;
                    } catch (_) {}
                    alert(errMsg);
                    return;
                }

                // Extract filename from Content-Disposition header, fallback to a sensible default
                let filename = `Facturas_${dateVal}.xlsx`;
                const disposition = res.headers.get('Content-Disposition');
                if (disposition) {
                    const match = disposition.match(/filename[^;=\n]*=(['"]?)([^'"\n;]+)\1/);
                    if (match && match[2]) {
                        filename = decodeURIComponent(match[2]);
                    }
                }

                const blob = await res.blob();
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
            } catch (e) {
                console.error('Excel export error:', e);
                alert('Error de conexión al descargar el archivo Excel.');
            } finally {
                this.loading = false;
            }
        },

        getStatusClass(status) {
            if (status === 'Cancelada') return 'bg-red-100 text-red-700';
            if (status === 'Cerrada') return 'bg-green-100 text-green-700';
            return 'bg-blue-100 text-blue-700';
        },

        async toggleFactura(invoiceNum, field, value) {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                const res = await fetch(`${cfg.ordersIndexUrl}api/facturas/${invoiceNum}/toggle`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ field, value, client_id: this.clientId })
                });
                const data = await res.json();
                if (!res.ok) {
                    alert((data.error || 'Error al actualizar estado') + (data.trace ? '\n\n' + data.trace : ''));
                    const inv = this.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
                    if (inv) inv[field] = !value; // revert
                    if (this.currentRelacion && this.currentRelacion.invoices) {
                        const relInv = this.currentRelacion.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
                        if (relInv) relInv[field] = !value;
                    }
                } else {
                    const inv = this.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
                    if (inv) inv[field] = value;
                    if (this.currentRelacion && this.currentRelacion.invoices) {
                        const relInv = this.currentRelacion.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
                        if (relInv) relInv[field] = value;
                    }
                    this.triggerAutoSaveRelacion();
                }
            } catch (e) {
                console.error(e);
                alert('Error de conexión');
                const inv = this.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
                if (inv) inv[field] = !value; // revert
                if (this.currentRelacion && this.currentRelacion.invoices) {
                    const relInv = this.currentRelacion.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
                    if (relInv) relInv[field] = !value;
                }
            }
        },

        async batchToggleEntrega(checked) {
            const targets = this.invoices.filter(i => i.status !== 'Cancelada');
            if (targets.length === 0) return;

            const action = checked ? 'marcar' : 'desmarcar';
            if (!confirm(`¿${checked ? 'Marcar' : 'Desmarcar'} entrega en ${targets.length} facturas?`)) {
                // Revert the checkbox since user canceled
                return;
            }

            // Set all locally first for instant feedback
            targets.forEach(inv => { inv.entrega = checked; });

            // Then sync with backend
            let errors = 0;
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
            for (const inv of targets) {
                try {
                    const res = await fetch(`${cfg.ordersIndexUrl}api/facturas/${inv.invoice_number}/toggle`, {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({ field: 'entrega', value: checked, client_id: this.clientId })
                    });
                    if (!res.ok) errors++;
                } catch (e) {
                    errors++;
                }
            }
            if (errors > 0) {
                alert(`⚠️ ${errors} factura(s) no pudieron ser actualizadas.`);
            }
            this.triggerAutoSaveRelacion();
        },

        editObservacion(inv) {
            inv._temp_observaciones = inv.observaciones || '';
            inv._editing = true;
        },

        handleCategoryDropdownChange(invoiceNum, newCategory, oldCategory) {
            this.pushUndo({
                type: 'category_change',
                invoiceNum,
                oldCategory,
                newCategory
            });
            this.updateCategory(invoiceNum, newCategory);
        },

        async updateCategory(invoiceNum, newCategory, isUndo = false) {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                const res = await fetch(`/orders/api/facturas/${invoiceNum}/category`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ category: newCategory, client_id: this.clientId })
                });
                
                if (!res.ok) {
                    const data = await res.json();
                    alert(data.error || 'Error al actualizar categoría');
                    return;
                }
                
                // Update local category and trigger delta update if selected
                const inv = this.invoices.find(i => String(i.invoice_number) === String(invoiceNum));
                if (inv) {
                    inv.shipping_type = newCategory;
                    if (inv._selected) {
                        this.toggleInvoiceSelection(inv, true);
                    }
                }
                
                // For a smooth experience, let's just trigger a data refresh
                this.fetchInvoices();
            } catch (e) {
                console.error(e);
                alert('Error de conexión al actualizar categoría');
            }
        },

        /** Raw swap: mutates manualOrder in-place for a single offset move. Used by arrow-key batch handler. */
        _rawOrderSwap(inv, offset) {
            const displayOrder = [];
            const categoryMap = {};
            this.invoiceGroups.forEach(g => {
                g.invoices.forEach(i => {
                    displayOrder.push(String(i.invoice_number));
                    categoryMap[String(i.invoice_number)] = g.category;
                });
            });

            const currentIndex = displayOrder.indexOf(String(inv.invoice_number));
            if (currentIndex === -1) return;
            const newIndex = currentIndex + offset;
            if (newIndex < 0 || newIndex >= displayOrder.length) return;

            const targetCategory = categoryMap[displayOrder[newIndex]];

            displayOrder.splice(currentIndex, 1);
            displayOrder.splice(newIndex, 0, String(inv.invoice_number));

            if (this.sortColumn !== 'manual') {
                this.manualOrder = displayOrder;
            } else {
                const currentOrderSet = new Set(this.manualOrder);
                displayOrder.forEach(id => currentOrderSet.delete(id));
                this.manualOrder = [...displayOrder, ...Array.from(currentOrderSet)];
            }
            this.sortColumn = 'manual';

            // Handle cross-category moves
            if (targetCategory && targetCategory !== (inv.shipping_type || 'LOCAL').toUpperCase()) {
                this.updateCategory(inv.invoice_number, targetCategory);
            }
        },

        moveRowByOffset(inv, offset) {
            const displayOrder = [];
            const categoryMap = {};
            this.invoiceGroups.forEach(g => {
                g.invoices.forEach(i => {
                    displayOrder.push(String(i.invoice_number));
                    categoryMap[String(i.invoice_number)] = g.category;
                });
            });
            
            const currentIndex = displayOrder.indexOf(String(inv.invoice_number));
            if (currentIndex === -1) return;
            const newIndex = currentIndex + offset;
            
            if (newIndex < 0 || newIndex >= displayOrder.length) return;
            
            const targetInvoiceNum = displayOrder[newIndex];
            const targetCategory = categoryMap[targetInvoiceNum];
            
            this.performOrderSwap(inv, currentIndex, newIndex, displayOrder, targetCategory);
        },

        changeRowPosition(inv, newPositionStr) {
            const newPosition = parseInt(newPositionStr, 10);
            if (isNaN(newPosition) || newPosition < 1) {
                inv._editing_position = false;
                return;
            }
            
            const displayOrder = [];
            const categoryMap = {};
            
            this.invoiceGroups.forEach(g => {
                g.invoices.forEach(i => {
                    displayOrder.push(String(i.invoice_number));
                    categoryMap[i._global_index - 1] = g.category;
                });
            });
            
            const currentIndex = displayOrder.indexOf(String(inv.invoice_number));
            if (currentIndex === -1) {
                inv._editing_position = false;
                return;
            }
            
            const targetIndex = Math.min(newPosition - 1, displayOrder.length - 1);
            if (currentIndex === targetIndex) {
                inv._editing_position = false;
                return;
            }
            
            const targetCategory = categoryMap[targetIndex] || 'LOCAL';
            
            this.performOrderSwap(inv, currentIndex, targetIndex, displayOrder, targetCategory);
            inv._editing_position = false;
        },

        performOrderSwap(inv, currentIndex, targetIndex, displayOrder, targetCategory) {
            const previousOrder = [...this.manualOrder];
            const previousSortColumn = this.sortColumn;
            const invoiceNum = String(inv.invoice_number);
            
            this.animateReorder(() => {
                displayOrder.splice(currentIndex, 1);
                displayOrder.splice(targetIndex, 0, invoiceNum);
                
                if (this.sortColumn !== 'manual') {
                    this.manualOrder = displayOrder;
                } else {
                    const currentOrderSet = new Set(this.manualOrder);
                    displayOrder.forEach(id => currentOrderSet.delete(id));
                    this.manualOrder = [...displayOrder, ...Array.from(currentOrderSet)];
                }
                this.sortColumn = 'manual';
                this.saveManualOrder();
                
                let catChange = null;
                if (targetCategory && targetCategory !== (inv.shipping_type || 'LOCAL').toUpperCase()) {
                     catChange = { invoiceNum: inv.invoice_number, oldCategory: inv.shipping_type || 'LOCAL', newCategory: targetCategory };
                     this.updateCategory(inv.invoice_number, targetCategory);
                }

                // Trigger Alpine re-render WITHOUT highlightInvoice (no extra spread here)
                this.invoices = [...this.invoices];

                this.pushUndo({
                    type: 'drag',
                    oldOrder: previousOrder,
                    oldSortColumn: previousSortColumn,
                    categoryChange: catChange
                });
            }, invoiceNum);

            // Highlight the moved row AFTER animation begins (avoids triggering
            // a second this.invoices spread inside the FLIP callback)
            setTimeout(() => {
                this.highlightInvoice(invoiceNum);
            }, 100);
        },

        editCreditoNotes(inv) {
            inv._temp_credito_notes = inv.credito_notes || '';
            inv._editing_credito_notes = true;
        },

        async saveCreditoNotes(inv) {
            if (!inv._editing_credito_notes) return;
            inv._editing_credito_notes = false;
            
            if (inv._temp_credito_notes === (inv.credito_notes || '')) {
                return;
            }

            const oldVal = inv.credito_notes;
            inv.credito_notes = inv._temp_credito_notes;

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                const res = await fetch(`${cfg.ordersIndexUrl}api/facturas/${inv.invoice_number}/credito-notes`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ notes: inv.credito_notes })
                });
                if (!res.ok) {
                    const data = await res.json();
                    alert(data.error || 'Error al guardar notas de crédito');
                    inv.credito_notes = oldVal;
                }
            } catch (e) {
                console.error(e);
                alert('Error de conexión al guardar notas de crédito');
                inv.credito_notes = oldVal;
            }
        },

        async saveObservacion(inv) {
            if (!inv._editing) return; // Prevent double trigger from enter + blur
            inv._editing = false;
            
            // If the value didn't change, do nothing
            if (inv._temp_observaciones === (inv.observaciones || '')) {
                return;
            }

            const oldVal = inv.observaciones;
            inv.observaciones = inv._temp_observaciones;

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                const res = await fetch(`${cfg.ordersIndexUrl}api/facturas/${inv.invoice_number}/toggle`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ field: 'observaciones', value: inv.observaciones, client_id: this.clientId })
                });
                if (!res.ok) {
                    const data = await res.json();
                    alert(data.error || 'Error al guardar observación');
                    inv.observaciones = oldVal;
                } else {
                    if (inv._selected) {
                        this.toggleInvoiceSelection(inv, true);
                    }
                }
            } catch (e) {
                console.error(e);
                alert('Error de conexión al guardar observación');
                inv.observaciones = oldVal;
            }
        },

        // ── Relación de Envíos Methods ──

        async fetchRelacionForDate() {
            try {
                const res = await fetch(`/orders/api/relaciones?date=${this.selectedDate}`);
                const data = await res.json();
                
                // Track previous selections to detect changes
                const prevSelected = new Set(
                    this.invoices.filter(i => i._selected).map(i => String(i.invoice_number))
                );

                this.currentRelacion = data.relacion || null;

                // Sync checkbox state from DB relationship to the invoices list
                if (this.currentRelacion && this.currentRelacion.invoices) {
                    const relInvoiceNums = new Set(this.currentRelacion.invoices.map(i => String(i.invoice_number)));
                    
                    const toHighlight = [];
                    this.invoices.forEach(i => {
                        const isSelectedNow = relInvoiceNums.has(String(i.invoice_number));
                        const wasSelectedBefore = prevSelected.has(String(i.invoice_number));
                        
                        if (isSelectedNow !== wasSelectedBefore) {
                            toHighlight.push(String(i.invoice_number));
                        }
                        i._selected = isSelectedNow;
                    });
                    
                    // Sync metadata (credito_notes, rebote, observaciones, etc.) from master list to relacion invoices
                    this.currentRelacion.invoices.forEach(relInv => {
                        const masterInv = this.invoices.find(i => String(i.invoice_number) === String(relInv.invoice_number));
                        if (masterInv) {
                            relInv.credito_notes = masterInv.credito_notes;
                            relInv.credito_authorized = masterInv.credito_authorized;
                            relInv.credito_authorized_name = masterInv.credito_authorized_name;
                            relInv.credito_authorized_by = masterInv.credito_authorized_by;
                            relInv.credito_authorized_at = masterInv.credito_authorized_at;
                            relInv.shipping_type = masterInv.shipping_type;
                            relInv.observaciones = masterInv.observaciones;
                            relInv.rebote = masterInv.rebote;
                            relInv.recibido = masterInv.recibido;
                            relInv.entrega = masterInv.entrega;
                        }
                    });

                    // Sync to localStorage
                    const selected = this.invoices.filter(i => i._selected).map(i => String(i.invoice_number));
                    localStorage.setItem('qb_facturas_selected_' + this.selectedDate, JSON.stringify(selected));

                    // Highlight changed items ONLY when it's an actual selection change
                    // (not when triggered by a manual-order sync, which only reorders without changing selections)
                    if (this.isInitialized && toHighlight.length > 0 && !this._suppressRelacionHighlight && typeof this.highlightInvoice === 'function') {
                        toHighlight.forEach(num => this.highlightInvoice(num));
                    }
                } else if (!this.currentRelacion && this.invoices.length > 0) {
                    const toHighlight = [];
                    // Clear checkbox selection if no relationship exists
                    this.invoices.forEach(i => {
                        if (i._selected) {
                            toHighlight.push(String(i.invoice_number));
                        }
                        i._selected = false;
                    });
                    localStorage.removeItem('qb_facturas_selected_' + this.selectedDate);
                    
                    if (this.isInitialized && toHighlight.length > 0 && !this._suppressRelacionHighlight && typeof this.highlightInvoice === 'function') {
                        toHighlight.forEach(num => this.highlightInvoice(num));
                    }
                }

                // Restore persisted signatures
                if (this.currentRelacion && this.currentRelacion.signatures) {
                    const sigs = this.currentRelacion.signatures;
                    this.signatures = {
                        facturacion: sigs.facturacion || null,
                        credito: sigs.credito || null,
                    };
                } else {
                    this.signatures = { facturacion: null, credito: null };
                }
            } catch (e) {
                console.error('Error fetching relacion:', e);
            }
        },

        async fetchRelaciones() {
            this.relacionLoading = true;
            try {
                const res = await fetch(`/orders/api/relaciones/list?date_from=${this.relacionDateFrom}&date_to=${this.relacionDateTo}`);
                const data = await res.json();
                this.relaciones = data.relaciones || [];
            } catch (e) {
                console.error('Error fetching relaciones:', e);
            } finally {
                this.relacionLoading = false;
            }
        },

        async toggleInvoiceSelection(invoices, selected) {
            const isArray = Array.isArray(invoices);
            const invoiceList = isArray ? invoices : [invoices];
            
            const dateVal = this.selectedDate;
            if (!dateVal || !/^\d{4}-\d{2}-\d{2}$/.test(dateVal)) return;

            // Optimistic update for instant feedback in Relaciones tab
            if (!this.currentRelacion) {
                this.currentRelacion = { invoices: [] };
            }

            const currentInvoices = this.currentRelacion.invoices || [];
            let updatedInvoices;
            const targetNums = new Set(invoiceList.map(i => String(i.invoice_number)));

            if (selected) {
                // Add missing
                const toAdd = invoiceList.filter(i => i.status !== 'Cancelada');
                // Remove existing instances to prevent duplicates
                const filtered = currentInvoices.filter(i => !targetNums.has(String(i.invoice_number)));
                updatedInvoices = [...filtered, ...toAdd];
                
                // Highlight locally added items
                if (typeof this.highlightInvoice === 'function') {
                    invoiceList.forEach(i => this.highlightInvoice(String(i.invoice_number)));
                }
            } else {
                // Remove
                updatedInvoices = currentInvoices.filter(i => !targetNums.has(String(i.invoice_number)));
                
                // Highlight locally removed items (in Facturas tab)
                if (typeof this.highlightInvoice === 'function') {
                    invoiceList.forEach(i => this.highlightInvoice(String(i.invoice_number)));
                }
            }

            // Create a completely new object reference to trigger deep reactivity in Alpine
            this.currentRelacion = {
                ...this.currentRelacion,
                invoices: this.sortInvoicesArray(updatedInvoices)
            };

            // Sync to local storage
            const selectedNums = this.invoices.filter(i => i._selected).map(i => String(i.invoice_number));
            localStorage.setItem('qb_facturas_selected_' + this.selectedDate, JSON.stringify(selectedNums));

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                
                const payload = {
                    date: dateVal,
                    selected: selected,
                    manual_order: this.manualOrder,
                    client_id: this.clientId
                };

                if (isArray) {
                    payload.invoice_numbers = invoiceList.map(i => String(i.invoice_number));
                    payload.invoice_data = invoiceList.map(i => ({
                        invoice_number: String(i.invoice_number),
                        order_number: i.order_number || '',
                        customer_name: i.customer_name,
                        total: i.total,
                        shipping_type: i.shipping_type || 'LOCAL',
                        observaciones: i.observaciones || '',
                        payment_terms: i.payment_terms || '',
                        status: i.status || ''
                    }));
                } else if (invoices) {
                    const i = invoices;
                    payload.invoice_number = String(i.invoice_number);
                    payload.invoice_data = {
                        invoice_number: String(i.invoice_number),
                        order_number: i.order_number || '',
                        customer_name: i.customer_name,
                        total: i.total,
                        shipping_type: i.shipping_type || 'LOCAL',
                        observaciones: i.observaciones || '',
                        payment_terms: i.payment_terms || '',
                        status: i.status || ''
                    };
                }

                const res = await fetch('/orders/api/relaciones/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    const data = await res.json();
                    this.currentRelacion = data.relacion;
                }
            } catch (e) {
                console.error('Error toggling invoice in relationship:', e);
            }
        },

        triggerAutoSaveRelacion() {
            clearTimeout(this.autoSaveTimeout);
            this.autoSaveTimeout = setTimeout(() => {
                this.generateRelacion();
            }, 500);
        },

        async generateRelacion() {
            const dateVal = this.selectedDate;
            if (!dateVal || !/^\d{4}-\d{2}-\d{2}$/.test(dateVal)) return;

            const hasSelected = this.invoices.some(i => i._selected);

            // If nothing is selected and there's no relationship on the server, do nothing
            if (!hasSelected && !this.currentRelacion) {
                return;
            }

            // Otherwise, save exactly what is selected (which could be empty if a relationship exists)
            let invoicesToSave = hasSelected
                ? this.invoices.filter(i => i._selected && i.status !== 'Cancelada')
                : [];

            invoicesToSave = this.sortInvoicesArray(invoicesToSave);

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                const saveRes = await fetch('/orders/api/relaciones', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ date: dateVal, invoices: invoicesToSave, client_id: this.clientId })
                });
                if (saveRes.ok) {
                    const saveData = await saveRes.json();
                    this.currentRelacion = saveData.relacion;
                }
            } catch (e) {
                console.error('Error autoguardando relacion:', e);
            }
        },

        async updateRelacionFromFacturas() {
            // Same as generateRelacion but called from the Relaciones tab
            // Updates the current relación with the latest facturas data
            const dateVal = this.selectedDate;
            if (!dateVal || !/^\d{4}-\d{2}-\d{2}$/.test(dateVal)) {
                alert('Fecha inválida.');
                return;
            }

            let invoicesToSave = this.invoices.filter(i => {
                if (i.status === 'Cancelada') return false;
                if (!i.credito_authorized) return false;
                return true;
            });
            invoicesToSave = this.sortInvoicesArray(invoicesToSave);

            if (invoicesToSave.length === 0) {
                alert('No hay facturas para actualizar.');
                return;
            }

            this.relacionLoading = true;
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                
                const saveRes = await fetch('/orders/api/relaciones', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ date: dateVal, invoices: invoicesToSave, client_id: this.clientId })
                });

                const saveData = await saveRes.json();
                if (!saveRes.ok) {
                    alert(saveData.error || 'Error al actualizar la relación');
                    return;
                }

                this.currentRelacion = saveData.relacion;
                
                // Refresh relaciones list
                this.fetchRelaciones();
            } catch (e) {
                console.error('Error updating relacion:', e);
                alert('Error de conexión al actualizar la relación.');
            } finally {
                this.relacionLoading = false;
            }
        },

        allSigned() {
            return !!this.signatures.facturacion && !!this.signatures.credito;
        },

        // ── Crédito y Cobranza Per-Invoice Authorization ──────────────────

        isCredito(inv) {
            return (inv.payment_terms || '').toUpperCase() !== 'CONTADO';
        },

        isContado(inv) {
            return (inv.payment_terms || '').toUpperCase() === 'CONTADO';
        },

        getAuthCellClass(inv, type) {
            const isApplicable = type === 'credito' ? this.isCredito(inv) : this.isContado(inv);
            if (!isApplicable) return 'auth-cell-na';
            if (inv.credito_authorized) return 'auth-cell-approved';
            return 'auth-cell-pending';
        },

        getAuthTooltip(inv) {
            if (!inv.credito_authorized) return 'Pendiente de autorización';
            const name = inv.credito_authorized_name || inv.credito_authorized_by || '';
            const at = inv.credito_authorized_at || '';
            let dateStr = '';
            if (at) {
                try {
                    const d = new Date(at);
                    dateStr = d.toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' });
                } catch(_) { dateStr = at; }
            }
            return `Autorizado por ${name}${dateStr ? ' el ' + dateStr : ''}`;
        },

        authorizationSummary() {
            if (!this.creditoTabInvoices) return { total: 0, authorized: 0, pending: 0 };
            const invoices = this.creditoTabInvoices;
            const total = invoices.length;
            const authorized = invoices.filter(i => i.credito_authorized).length;
            return { total, authorized, pending: total - authorized };
        },

        async authorizeInvoice(inv) {
            if (!this.canAuthorizarCredito) {
                alert('Solo el departamento de Crédito y Cobranza puede autorizar envíos.');
                return;
            }

            const newValue = !inv.credito_authorized;

            try {
                const res = await fetch(`/orders/api/facturas/${inv.invoice_number}/authorize`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        invoice_number: inv.invoice_number,
                        authorized: newValue,
                    }),
                });
                const data = await res.json();
                if (data.success && data.invoice) {
                    // Update the local invoice data
                    Object.assign(inv, data.invoice);
                } else {
                    alert(data.error || 'Error al autorizar factura');
                }
            } catch (e) {
                console.error('Error authorizing invoice:', e);
                // Optimistic update
                inv.credito_authorized = newValue;
                if (newValue) {
                    inv.credito_authorized_name = this.currentUserFullName;
                    inv.credito_authorized_at = new Date().toISOString();
                }
            }
        },

        async reprintRelacion(folio) {
            // Warn if not all signatures are set
            if (!this.allSigned()) {
                if (!confirm('No se han juntado todas las firmas, ¿seguro que quieres descargar?')) {
                    return;
                }
            }
            this.relacionLoading = true;
            try {
                const res = await fetch(`/orders/api/relaciones/${folio}/export`);
                if (!res.ok) {
                    let errMsg = 'Error al reimprimir.';
                    try { const ed = await res.json(); errMsg = ed.error || errMsg; } catch(_) {}
                    alert(errMsg);
                    return;
                }

                let filename = `Relacion_Envios_${folio}.xlsx`;
                const disposition = res.headers.get('Content-Disposition');
                if (disposition) {
                    const match = disposition.match(/filename[^;=\n]*=(['"]?)([^'"\n;]+)\1/);
                    if (match && match[2]) filename = decodeURIComponent(match[2]);
                }

                const blob = await res.blob();
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
            } catch (e) {
                console.error('Error reprinting relacion:', e);
                alert('Error de conexión al reimprimir.');
            } finally {
                this.relacionLoading = false;
            }
        },

        async cerrarDia() {
            const dateVal = this.selectedDate;

            // Collect unsent invoices (not canceled, not delivered)
            const unsentInvoices = this.invoices
                .filter(i => i.status !== 'Cancelada' && !i.entrega)
                .map(i => ({
                    invoice_number: i.invoice_number,
                    customer_name: i.customer_name,
                    total: i.total,
                    shipping_type: i.shipping_type,
                    order_number: i.order_number,
                    order_date: i.order_date,
                    invoice_date: i.invoice_date,
                    payment_terms: i.payment_terms,
                    paid_to_date: i.paid_to_date,
                    currency: i.currency,
                    observaciones: i.observaciones || '',
                }));

            const totalInvoices = this.invoices.filter(i => i.status !== 'Cancelada').length;
            const deliveredCount = totalInvoices - unsentInvoices.length;
            const displayDate = dateVal.split('-').reverse().join('/');

            let confirmMsg = `¿Está seguro que desea cerrar el día ${displayDate}?\n\n`;
            confirmMsg += `📊 Resumen:\n`;
            confirmMsg += `  ✅ Entregadas: ${deliveredCount} de ${totalInvoices}\n`;
            if (unsentInvoices.length > 0) {
                confirmMsg += `  📦 Pendientes (se moverán al siguiente día hábil): ${unsentInvoices.length}\n`;
            }
            confirmMsg += `\n⚠️ Esta acción no se puede deshacer.`;

            if (!confirm(confirmMsg)) {
                return;
            }

            this.relacionLoading = true;
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
                const res = await fetch('/orders/api/relaciones/cerrar-dia', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ date: dateVal, unsent_invoices: unsentInvoices })
                });

                const data = await res.json();
                if (!res.ok) {
                    alert(data.error || 'Error al cerrar el día');
                    return;
                }

                let msg = `✅ Día cerrado exitosamente.\nFolio: ${data.closed_folio}`;
                if (data.rolled_invoices > 0) {
                    msg += `\n\n📦 ${data.rolled_invoices} factura(s) movidas al siguiente día hábil: ${data.next_business_day.split('-').reverse().join('/')}`;
                    if (data.next_folio) msg += `\nNuevo folio: ${data.next_folio}`;
                }
                alert(msg);

                // Navigate to the next business day
                if (data.next_business_day) {
                    this.selectedDate = data.next_business_day;
                }

                // Refresh data
                await this.fetchInvoices();
                await this.fetchRelacionForDate();
                await this.fetchRelaciones();
            } catch (e) {
                console.error('Error closing day:', e);
                alert('Error de conexión al cerrar el día.');
            } finally {
                this.relacionLoading = false;
            }
        }
    }
}
