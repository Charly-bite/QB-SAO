

function facturasApp() {
    return {
        invoices: [],
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
        sapAvailable: null,
        canEditFacturas: null,
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
        activeTab: localStorage.getItem('qb_facturas_active_tab') || 'facturas',
        currentRelacion: null,
        relaciones: [],
        relacionLoading: false,
        relacionDateFrom: new Date(Date.now() - 30*86400000).toISOString().split('T')[0],
        relacionDateTo: new Date().toISOString().split('T')[0],
        autoSaveTimeout: null,
        // Signature state
        currentUserUsername: 'null',
        currentUserFullName: 'null',
        signatures: { facturacion: null, credito: null, almacen: null },
        canSignFacturacion: null,
        canSignCredito: null,
        canSignAlmacen: null,

        // Context Menu & Relationship Map State
        contextMenuShow: false,
        contextMenuX: 0,
        contextMenuY: 0,
        selectedInvoiceForMenu: null,
        relationshipMapShow: false,
        relationshipMapLoading: false,
        relationshipMapData: null,

        showContextMenu(event, inv) {
            if (this.activeTab !== 'facturas') return;
            this.selectedInvoiceForMenu = inv;
            this.contextMenuX = event.clientX;
            this.contextMenuY = event.clientY;
            this.contextMenuShow = true;
        },

        closeRelationshipMap() {
            this.relationshipMapShow = false;
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
            this.relationshipMapLoading = true;
            this.relationshipMapData = null;
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
                    almacen: this.canSignAlmacen,
                };
                if (!canSign[area]) {
                    const labels = {
                        facturacion: 'Facturación',
                        credito: 'Crédito y Cobranza',
                        almacen: 'Almacén',
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
                        almacen: data.signatures.almacen || null,
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
                    this.signatures[area] = { name: this.currentUserFullName };
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

        triggerAutoSaveRelacion() {
            if (this.autoSaveTimeout) clearTimeout(this.autoSaveTimeout);
            this.autoSaveTimeout = setTimeout(() => {
                this.generateRelacion();
            }, 1000);
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

                    // Temporarily disable undo pushing for each individual move
                    const originalPushUndo = this.pushUndo;
                    this.pushUndo = () => {};
                    
                    const previousOrder = [...this.manualOrder];
                    const previousSortColumn = this.sortColumn;

                    selectedInvoices.forEach(inv => {
                        this.moveRowByOffset(inv, offset);
                    });

                    // Restore undo and push a single bulk undo action
                    this.pushUndo = originalPushUndo;
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
                        body: JSON.stringify({ color: targetColor })
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
            const num = prompt("Introduce el número de factura a añadir:");
            if (num && !isNaN(num) && num.trim() !== "") {
                const numInt = parseInt(num, 10);
                if (!this.extraInvoices.includes(numInt)) {
                    this.extraInvoices.push(numInt);
                    await this.saveExtraInvoices();
                    this.fetchInvoices();
                } else {
                    alert("Esa factura ya está en la lista.");
                }
            }
        },

        async saveExtraInvoices() {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                await fetch('/orders/api/facturas/extra', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ date: this.selectedDate, extra_invoices: this.extraInvoices })
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
                        body: JSON.stringify({ customer_name: newName })
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
            return this.invoices.length > 0 && this.invoices.every(i => i._selected);
        },

        toggleAll() {
            const state = !this.allSelected;
            this.invoices.forEach(i => i._selected = state);
            this.saveSelection();
        },

        saveSelection() {
            this.$nextTick(() => {
                const selected = this.invoices.filter(i => i._selected).map(i => String(i.invoice_number));
                localStorage.setItem('qb_facturas_selected_' + this.selectedDate, JSON.stringify(selected));
                this.triggerAutoSaveRelacion();
            });
        },

        lastCheckedIndex: null,

        handleCheck(evt, inv) {
            if (evt.shiftKey && this.lastCheckedIndex !== null) {
                const start = Math.min(this.lastCheckedIndex, inv._global_index);
                const end = Math.max(this.lastCheckedIndex, inv._global_index);
                const targetState = evt.target.checked;
                
                this.invoices.forEach(i => {
                    if (i._global_index && i._global_index >= start && i._global_index <= end) {
                        i._selected = targetState;
                    }
                });
                window.getSelection().removeAllRanges();
            }
            this.lastCheckedIndex = inv._global_index;
            this.saveSelection();
        },

        handleRowClick(evt, inv) {
            if (['INPUT', 'BUTTON', 'A', 'TEXTAREA', 'SELECT', 'SVG', 'path'].includes(evt.target.tagName)) return;
            if (evt.target.closest('.drag-handle')) return;
            
            if (evt.ctrlKey || evt.metaKey) {
                inv._selected = !inv._selected;
                this.lastCheckedIndex = inv._global_index;
                window.getSelection().removeAllRanges();
                this.saveSelection();
            } else if (evt.shiftKey && this.lastCheckedIndex !== null) {
                const start = Math.min(this.lastCheckedIndex, inv._global_index);
                const end = Math.max(this.lastCheckedIndex, inv._global_index);
                const targetState = true;
                
                this.invoices.forEach(i => {
                    if (i._global_index && i._global_index >= start && i._global_index <= end) {
                        i._selected = targetState;
                    }
                });
                this.lastCheckedIndex = inv._global_index;
                window.getSelection().removeAllRanges();
                this.saveSelection();
            }
        },

        get invoiceGroups() {
            const groups = {};
            const categoryOrder = [
                'LOCAL', 'ENVIO LOCAL', 'PAQUETERIA', 'PASE A PAQUETERIA', 
                'PASE DIRECTO', 'PASE PROGRAMADO', 'FLETE INTERNO', 'FORANEO', 
                'ANEXADAS MTY', 'ANEXADAS GDL', 'ANEXADAS IRP'
            ];

            this.filteredInvoices.forEach(i => {
                let s = (i.shipping_type || 'LOCAL').toUpperCase();
                if (s === 'ANEXO MY' || s === 'ANEXO MTY') s = 'ANEXADAS MTY';
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
            if (!this.currentRelacion || !this.currentRelacion.invoices) return [];
            const groups = {};
            const categoryOrder = [
                'LOCAL', 'ENVIO LOCAL', 'PAQUETERIA', 'PASE A PAQUETERIA', 
                'PASE DIRECTO', 'PASE PROGRAMADO', 'FLETE INTERNO', 'FORANEO', 
                'ANEXADAS MTY', 'ANEXADAS GDL', 'ANEXADAS IRP'
            ];

            this.currentRelacion.invoices.forEach(inv => {
                const liveInv = this.invoices.find(i => String(i.invoice_number) === String(inv.invoice_number));
                const resolvedInv = liveInv ? { ...inv, ...liveInv } : inv;

                let cat = (resolvedInv.shipping_type || resolvedInv.observaciones || resolvedInv.nota || 'LOCAL').toUpperCase();
                if (cat === 'ANEXO MY' || cat === 'ANEXO MTY') cat = 'ANEXADAS MTY';
                if (cat === 'ANEXO GDL') cat = 'ANEXADAS GDL';
                if (cat === 'ANEXO IRP') cat = 'ANEXADAS IRP';

                if (!groups[cat]) {
                    groups[cat] = { category: cat, invoices: [] };
                }
                groups[cat].invoices.push(resolvedInv);
            });

            const invoiceIndexMap = new Map();
            this.invoices.forEach((inv, idx) => {
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

        async handleSSEEvent(data) {
            if (!data || !data.type) return;

            if (data.type === 'factura_category_changed') {
                const inv = this.invoices.find(i => i.invoice_number === data.invoice_number);
                if (inv) {
                    inv.shipping_type = data.category;
                    this.invoices = [...this.invoices];
                }
            } else if (data.type === 'factura_color_changed') {
                this.rowColors[data.invoice_number] = data.color;
                this.rowColors = { ...this.rowColors };
            } else if (data.type === 'factura_customer_name_changed') {
                if (data.customer_name) {
                    this.customCustomerNames[data.invoice_number] = data.customer_name;
                } else {
                    delete this.customCustomerNames[data.invoice_number];
                }
                this.customCustomerNames = { ...this.customCustomerNames };
            } else if (data.type === 'factura_manual_order_changed') {
                if (data.date === this.selectedDate) {
                    this.manualOrder = data.manual_order;
                    this.sortColumn = 'manual';
                    this.invoices = [...this.invoices];
                }
            } else if (data.type === 'factura_extras_changed') {
                if (data.date === this.selectedDate) {
                    this.extraInvoices = data.extra_invoices;
                    this.fetchInvoices();
                }
            } else if (data.type === 'order_updated' && data.order) {
                const updatedOrder = data.order;
                const inv = this.invoices.find(i => String(i.invoice_number) === String(updatedOrder.factura_number) || String(i.related_order_id) === String(data.order_id));
                if (inv) {
                    const statusVal = updatedOrder.status;
                    inv.recibido = statusVal === 'Listo' || statusVal === 'Entregado';
                    inv.entrega = statusVal === 'Entregado';
                    inv.observaciones = updatedOrder.observaciones || '';
                    this.invoices = [...this.invoices];
                }
            } else if (data.type === 'relacion_updated') {
                if (data.date === this.selectedDate && data.username !== this.currentUserUsername) {
                    await this.fetchRelacionForDate();
                }
            } else if (data.type === 'factura_observaciones_changed') {
                const inv = this.invoices.find(i => i.invoice_number === data.invoice_number);
                if (inv) {
                    inv.observaciones = data.observaciones;
                    this.invoices = [...this.invoices];
                }
            } else if (data.type === 'relacion_signature_changed') {
                if (this.currentRelacion && this.currentRelacion.folio === data.folio) {
                    this.currentRelacion.signatures = data.signatures;
                    this.signatures = {
                        facturacion: data.signatures.facturacion || null,
                        credito: data.signatures.credito || null,
                        almacen: data.signatures.almacen || null,
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
                ghostClass: 'bg-amber-50',
                scroll: true,
                bubbleScroll: true,
                scrollSensitivity: 60,
                scrollSpeed: 15,
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
                        
                        this.pushUndo({
                            type: 'drag',
                            oldOrder: previousOrder,
                            oldSortColumn: previousSortColumn,
                            categoryChange: catChange
                        });
                    }
                }
            });
        },

        async saveManualOrder() {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                await fetch('/orders/api/facturas/manual-order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ date: this.selectedDate, manual_order: this.manualOrder })
                });
                this.triggerAutoSaveRelacion();
            } catch(e) { console.error('Error saving manual order:', e); }
        },

        loadManualOrder() {},





        async fetchInvoices() {
            if (this.loading) return;
            this.loading = true;
            this.errorMsg = '';

            try {
                let params = this.selectedDate ? '?date=' + this.selectedDate : '';
                const res = await fetch("null" + params + (params ? '&' : '?') + '_=' + Date.now(), { cache: 'no-store' });
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

                    this.invoices = (data.invoices || []).map(i => ({ 
                        ...i, 
                        _editing: false, 
                        _temp_observaciones: '',
                        _editing_customer: false,
                        _temp_customer: '',
                        _selected: selectedInvoiceNumbers.has(String(i.invoice_number)),
                        _editing_position: false
                    }));
                    this.stats = data.stats || {};
                    await this.fetchRelacionForDate();
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

        sortBy(column) {
            if (this.sortColumn === column) {
                this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortColumn = column;
                this.sortDir = 'desc';
            }
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

            // No DOM sync needed as Alpine state is preserved automatically across fetches

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
                const url = `null`;
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
                const res = await fetch(`nullapi/facturas/${invoiceNum}/toggle`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ field, value })
                });
                const data = await res.json();
                if (!res.ok) {
                    alert(data.error || 'Error al actualizar estado');
                    const inv = this.invoices.find(i => i.invoice_number === invoiceNum);
                    if (inv) inv[field] = !value; // revert
                } else {
                    this.triggerAutoSaveRelacion();
                }
            } catch (e) {
                console.error(e);
                alert('Error de conexión');
                const inv = this.invoices.find(i => i.invoice_number === invoiceNum);
                if (inv) inv[field] = !value; // revert
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
            for (const inv of targets) {
                try {
                    const res = await fetch(`nullapi/facturas/${inv.invoice_number}/toggle`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ field: 'entrega', value: checked })
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
            if (!inv.related_order_id) {
                alert('Esta factura no tiene un pedido local vinculado. No se puede agregar nota.');
                return;
            }
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
                    body: JSON.stringify({ category: newCategory })
                });
                
                if (!res.ok) {
                    const data = await res.json();
                    alert(data.error || 'Error al actualizar categoría');
                    return;
                }
                
                // If the new category changes its group, we must reload the page or fetch data
                // For a smooth experience, let's just trigger a data refresh
                this.fetchInvoices();
                this.triggerAutoSaveRelacion();
            } catch (e) {
                console.error(e);
                alert('Error de conexión al actualizar categoría');
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
            
            displayOrder.splice(currentIndex, 1);
            displayOrder.splice(targetIndex, 0, String(inv.invoice_number));
            
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
            
            this.pushUndo({
                type: 'drag',
                oldOrder: previousOrder,
                oldSortColumn: previousSortColumn,
                categoryChange: catChange
            });
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
                const res = await fetch(`nullapi/facturas/${inv.invoice_number}/toggle`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ field: 'observaciones', value: inv.observaciones })
                });
                if (!res.ok) {
                    const data = await res.json();
                    alert(data.error || 'Error al guardar observación');
                    inv.observaciones = oldVal;
                } else {
                    this.triggerAutoSaveRelacion();
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
                this.currentRelacion = data.relacion || null;

                // Sync checkbox state from DB relationship to the invoices list
                if (this.currentRelacion && this.currentRelacion.invoices) {
                    const relInvoiceNums = new Set(this.currentRelacion.invoices.map(i => String(i.invoice_number)));
                    this.invoices.forEach(i => {
                        i._selected = relInvoiceNums.has(String(i.invoice_number));
                    });
                    // Sync to localStorage
                    const selected = this.invoices.filter(i => i._selected).map(i => String(i.invoice_number));
                    localStorage.setItem('qb_facturas_selected_' + this.selectedDate, JSON.stringify(selected));
                } else if (!this.currentRelacion && this.invoices.length > 0) {
                    // Clear checkbox selection if no relationship exists
                    this.invoices.forEach(i => {
                        i._selected = false;
                    });
                    localStorage.removeItem('qb_facturas_selected_' + this.selectedDate);
                }

                // Restore persisted signatures
                if (this.currentRelacion && this.currentRelacion.signatures) {
                    const sigs = this.currentRelacion.signatures;
                    this.signatures = {
                        facturacion: sigs.facturacion || null,
                        credito: sigs.credito || null,
                        almacen: sigs.almacen || null,
                    };
                } else {
                    this.signatures = { facturacion: null, credito: null, almacen: null };
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

        triggerAutoSaveRelacion() {
            clearTimeout(this._relacionSaveTimeout);
            this._relacionSaveTimeout = setTimeout(() => {
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
                    body: JSON.stringify({ date: dateVal, invoices: invoicesToSave })
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

            let invoicesToSave = this.invoices.filter(i => i.status !== 'Cancelada');
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
                    body: JSON.stringify({ date: dateVal, invoices: invoicesToSave })
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
            return !!this.signatures.facturacion && !!this.signatures.credito && !!this.signatures.almacen;
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

