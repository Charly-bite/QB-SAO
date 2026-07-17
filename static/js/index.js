/* ══════════════════════════════════════════════════════
   index.js — Alpine.js app logic for the Orders Monitor page
   Extracted from templates/orders/index.html

   Server-side values are injected via window.__indexConfig
   which is set in the template before this script loads.
   ══════════════════════════════════════════════════════ */

function indexData() {
    const cfg = window.__indexConfig || {};
    return {
        orders: cfg.orders || [],
        timer: 10,
        loading: false,
        searchQuery: '',
        dateFrom: (function() {
            try {
                const saved = localStorage.getItem('qb_orders_date_from');
                return saved !== null ? saved : new Date().toISOString().split('T')[0];
            } catch (e) {
                return new Date().toISOString().split('T')[0];
            }
        })(),
        dateTo: (function() {
            try {
                const saved = localStorage.getItem('qb_orders_date_to');
                return saved !== null ? saved : new Date().toISOString().split('T')[0];
            } catch (e) {
                return new Date().toISOString().split('T')[0];
            }
        })(),
        maxOrders: '50',
        activeTopFilter: 'all',
        activeStats: {},
        totalPages: 1,
        currentPage: 1,
        pageSize: 50,
        sortBy: 'order_id',
        sortDesc: true,
        savedViews: [],
        navigatingTo: null,

        navigateToOrder(id) {
            if (this.navigatingTo) return;
            this.navigatingTo = id;
            setTimeout(() => {
                window.location.href = `/orders/${id}`;
            }, 150);
        },

        get baseFilteredOrders() {
            const q = (this.searchQuery || '').toLowerCase().trim();
            const from = this.dateFrom || '', to = this.dateTo || '';
            
            return this.orders.filter(o => {
                // Date range filter
                if (from || to) {
                    const rawDate = o.order_date || o.doc_date || '';
                    if (!rawDate) return false;
                    const oDate = rawDate.split('T')[0].split(' ')[0];
                    if (from && oDate < from) return false;
                    if (to && oDate > to) return false;
                }
                // Text search
                if (!q) return true;
                return String(o.order_id).includes(q) ||
                    (o.customer_name || '').toLowerCase().includes(q) ||
                    (o.customer_code || '').toLowerCase().includes(q) ||
                    (o.factura_number && String(o.factura_number).includes(q)) ||
                    (o.delivery_number && String(o.delivery_number).includes(q)) ||
                    (o.created_by || '').toLowerCase().includes(q);
            });
        },

        get activeStats() {
            const c = { total_active: 0, pending: 0, in_progress: 0, picking: 0, invoicing: 0, ready: 0, shipped: 0, waiting: 0, cancelled: 0 };
            for (const o of this.baseFilteredOrders) {
                if (o.status !== 'Cancelado') c.total_active++; // Active means not cancelled? Wait, original counted everything.
                // Reverting to counting everything for total_active
            }
            const counts = { total_active: 0, pending: 0, in_progress: 0, picking: 0, invoicing: 0, ready: 0, shipped: 0, waiting: 0, cancelled: 0 };
            for (const o of this.baseFilteredOrders) {
                counts.total_active++;
                if (o.status === 'Pendiente') counts.pending++;
                if (o.status === 'En Proceso') counts.in_progress++;
                if (o.status === 'Entregado' || o.status === 'Preparando') counts.picking++;
                if (o.status === 'Facturacion') counts.invoicing++;
                if (o.status === 'Relacion de envio' || o.status === 'Recibido por almacen') counts.ready++;
                if (o.status === 'Enviado al cliente') counts.shipped++;
                if (o.status === 'En Espera') counts.waiting++;
                if (o.status === 'Cancelado') counts.cancelled++;
            }
            return counts;
        },

        orderMatchesTopFilter(o) {
            if (this.activeTopFilter === 'all') return true;
            if (this.activeTopFilter === 'pending') return o.status === 'Pendiente';
            if (this.activeTopFilter === 'process') return o.status === 'En Proceso';
            if (this.activeTopFilter === 'picking') return o.status === 'Entregado' || o.status === 'Preparando';
            if (this.activeTopFilter === 'invoice') return o.status === 'Facturacion';
            if (this.activeTopFilter === 'relation') return o.status === 'Relacion de envio' || o.status === 'Recibido por almacen';
            if (this.activeTopFilter === 'shipped') return o.status === 'Enviado al cliente';
            if (this.activeTopFilter === 'waiting') return o.status === 'En Espera';
            if (this.activeTopFilter === 'cancelled') return o.status === 'Cancelado';
            return true;
        },

        toggleTopFilter(f) { this.activeTopFilter = this.activeTopFilter === f ? 'all' : f; this.currentPage = 1; },
        getTopFilterLabel() {
            const m = {
                'pending': 'Pendientes',
                'process': 'En Proceso',
                'picking': 'Entregados',
                'invoice': 'Facturados',
                'relation': 'Relación',
                'shipped': 'Enviados',
                'waiting': 'En Espera',
                'cancelled': 'Cancelado'
            };
            return m[this.activeTopFilter] || 'Filtro';
        },
        
        // --- Saved Views Logic ---
        saveCurrentView() {
            const name = prompt("Nombre para esta vista guardada:");
            if (!name) return;
            const view = {
                name: name,
                filters: {
                    searchQuery: this.searchQuery,
                    dateFrom: this.dateFrom,
                    dateTo: this.dateTo,
                    activeTopFilter: this.activeTopFilter,
                    maxOrders: this.maxOrders,
                    sortBy: this.sortBy,
                    sortDesc: this.sortDesc
                }
            };
            this.savedViews.push(view);
            localStorage.setItem('qb_saved_views', JSON.stringify(this.savedViews));
        },
        
        applyView(view) {
            this.searchQuery = view.filters.searchQuery || '';
            this.dateFrom = view.filters.dateFrom || '';
            this.dateTo = view.filters.dateTo || '';
            this.activeTopFilter = view.filters.activeTopFilter || 'all';
            this.maxOrders = view.filters.maxOrders || '50';
            this.sortBy = view.filters.sortBy || 'order_id';
            this.sortDesc = view.filters.sortDesc !== undefined ? view.filters.sortDesc : true;
            this.currentPage = 1;
        },
        
        deleteView(index) {
            this.savedViews.splice(index, 1);
            localStorage.setItem('qb_saved_views', JSON.stringify(this.savedViews));
        },
        
        // --- Excel Export ---
        exportToExcel() {
            if (!window.XLSX) {
                alert("La librería de exportación aún está cargando. Por favor, intenta en unos segundos.");
                return;
            }
            
            // Map current filtered orders to a clean format for Excel
            const exportData = this.filteredOrders.map(o => ({
                'ID Pedido': o.order_id,
                'Cliente': o.customer_name || 'N/A',
                'Código Cliente': o.customer_code || 'N/A',
                'Fecha': this.formatDate(o.created_at),
                'Total': o.total,
                'Status': o.status,
                'Términos': o.payment_group || 'N/A',
                'Factura': o.factura_number || 'N/A',
                'Envío': o.shipping_type || 'N/A',
                'Vendedor': o.seller_name || 'N/A',
                'Comentarios': o.comments || ''
            }));
            
            const ws = XLSX.utils.json_to_sheet(exportData);
            
            // Auto-size columns slightly
            const wscols = [
                {wch: 10}, // ID
                {wch: 40}, // Cliente
                {wch: 15}, // Codigo
                {wch: 12}, // Fecha
                {wch: 12}, // Total
                {wch: 20}, // Status
                {wch: 15}, // Terminos
                {wch: 12}, // Factura
                {wch: 20}, // Envio
                {wch: 30}, // Vendedor
                {wch: 40}  // Comentarios
            ];
            ws['!cols'] = wscols;
            
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, "Pedidos");
            
            const dateStr = new Date().toISOString().split('T')[0];
            XLSX.writeFile(wb, `Pedidos_QBSAO_${dateStr}.xlsx`);
        },

        toggleSort(col) {
            if (this.sortBy === col) { this.sortDesc = !this.sortDesc; }
            else { this.sortBy = col; this.sortDesc = true; }
            this.currentPage = 1;
        },

        get sortedOrders() {
            let r = this.baseFilteredOrders.filter(o => this.orderMatchesTopFilter(o));
            r.sort((a, b) => {
                let aVal = a[this.sortBy] || "", bVal = b[this.sortBy] || "";
                if (this.sortBy === 'items_count') {
                    aVal = (a.items || []).length; bVal = (b.items || []).length;
                } else if (this.sortBy === 'order_id') {
                    aVal = parseInt(aVal) || 0; bVal = parseInt(bVal) || 0;
                } else if (this.sortBy === 'order_date') {
                    aVal = a.order_date || a.doc_date || ""; bVal = b.order_date || b.doc_date || "";
                } else if (this.sortBy === 'updated_at') {
                    aVal = a.last_updated || a.imported_at || ""; bVal = b.last_updated || b.imported_at || "";
                } else {
                    aVal = String(aVal).toLowerCase(); bVal = String(bVal).toLowerCase();
                }
                
                if (aVal < bVal) return this.sortDesc ? 1 : -1;
                if (aVal > bVal) return this.sortDesc ? -1 : 1;
                return 0;
            });
            return r;
        },

        get filteredOrders() {
            const max = parseInt(this.maxOrders) || 0;
            let r = this.sortedOrders;
            if (max > 0 && r.length > max) r = r.slice(0, max);
            return r;
        },

        get totalPages() { return Math.max(1, Math.ceil(this.filteredOrders.length / this.pageSize)); },
        get pageStartIdx() { return (this.currentPage - 1) * this.pageSize; },
        get pageEndIdx() { return this.pageStartIdx + this.pageSize; },
        get paginatedOrders() {
            if (this.currentPage > this.totalPages) this.currentPage = this.totalPages;
            if (this.currentPage < 1) this.currentPage = 1;
            return this.filteredOrders.slice(this.pageStartIdx, this.pageEndIdx);
        },
        get pageNumbers() {
            const t = this.totalPages, c = this.currentPage;
            if (t <= 7) return Array.from({ length: t }, (_, i) => i + 1);
            const p = [1];
            if (c > 3) p.push('...');
            for (let i = Math.max(2, c - 1); i <= Math.min(t - 1, c + 1); i++) p.push(i);
            if (c < t - 2) p.push('...');
            p.push(t);
            return p;
        },
        goToPage(page) {
            if (page < 1 || page > this.totalPages) return;
            this.currentPage = page;
            document.querySelector('.qb-table-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        },

        init() {
            const params = new URLSearchParams(window.location.search);
            const st = params.get('status');
            if (st) {
                const map = { 'Pendiente': 'pending', 'En Proceso': 'process', 'Terminado': 'process', 'Preparando': 'process', 'Facturacion': 'invoice', 'Relacion de envio': 'relation', 'Recibido por almacen': 'relation', 'Enviado al cliente': 'shipped', 'En Espera': 'waiting', 'Cancelado': 'cancelled' };
                if (map[st]) this.activeTopFilter = map[st];
            }
            // Load saved views
            try {
                const saved = localStorage.getItem('qb_saved_views');
                if (saved) this.savedViews = JSON.parse(saved);
            } catch(e) { console.warn(e); }

            // Watch date range filters to persist them
            this.$watch('dateFrom', val => {
                try {
                    localStorage.setItem('qb_orders_date_from', val !== null && val !== undefined ? val : '');
                } catch(e) { console.warn(e); }
            });
            this.$watch('dateTo', val => {
                try {
                    localStorage.setItem('qb_orders_date_to', val !== null && val !== undefined ? val : '');
                } catch(e) { console.warn(e); }
            });
        },

        async refreshData() {
            if (this.loading) return;
            this.loading = true;
            try {
                // Fetch all orders without status filter so Alpine has the full picture
                const res = await fetch(`/orders/api/refresh?_=${Date.now()}`, { cache: "no-store" });
                if (res.ok) {
                    const data = await res.json();
                    this.orders = data.orders;
                }
            } catch (e) { console.error("Refresh failed:", e); }
            finally { this.loading = false; }
        },



        formatDate(s) {
            if (!s) return '-';
            // Handle YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            const clean = String(s).split('T')[0].split(' ')[0];
            if (clean.match(/^\d{4}-\d{2}-\d{2}$/)) {
                const [y, m, d] = clean.split('-');
                return `${d}/${m}/${y}`;
            }
            return clean;
        },
        formatDateTime(s) {
            if (!s) return '-';
            const raw = String(s).substring(0, 16).replace('T', ' ');
            const parts = raw.split(' ');
            if (parts.length === 2 && parts[0].match(/^\d{4}-\d{2}-\d{2}$/)) {
                const [y, m, d] = parts[0].split('-');
                return `${d}/${m}/${y} ${parts[1]}`;
            }
            return raw;
        },

        getStatusBadgeClass(status) {
            return { 'Pendiente': 'badge-pendiente', 'En Proceso': 'badge-proceso', 'Entregado': 'badge-terminado', 'Preparando': 'badge-terminado', 'Facturacion': 'badge-facturado', 'Relacion de envio': 'badge-relacion', 'Recibido por almacen': 'badge-relacion', 'Enviado al cliente': 'badge-enviado', 'Cancelado': 'badge-cancelado', 'En Espera': 'badge-espera' }[status] || 'badge-pendiente';
        },

        getSapBadgeClass(status) {
            if (status === "Abierto") return "sap-abierto";
            if (status === "Cerrado") return "sap-cerrado";
            if (status === "Cancelado") return "sap-cancelado";
            return "badge-pendiente";
        }
    }
}
