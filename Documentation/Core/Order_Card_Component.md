---
tags:
  - open-oms/docs
  - ui-components
---

# Componente Order Card (Tarjeta de Pedido)

Este documento proporciona el contexto técnico, la estructura HTML, las hojas de estilo CSS y la lógica interactiva en Javascript (Alpine.js) necesarias para reutilizar la **Order Card** en otros desarrollos del sistema, manteniendo intacta la consistencia visual y de diseño premium.

---

## 1. Contexto del Componente

La **Order Card** es un componente visual interactivo diseñado para representar de manera clara y moderna el estado de un pedido en tiempo real. 

### Características Clave:
* **Indicador Lateral Dinámico (Accent Bar):** Una barra vertical en el borde izquierdo cuyo color cambia según el estado actual del pedido.
* **Información del Cliente y Vendedor:** Despliega el nombre del cliente, su código único y una etiqueta destacada para el vendedor.
* **Línea de Tiempo de Progreso (Stepper):** Muestra el flujo de vida del pedido (`PEND`, `PROC`, `FACT`, `REL`, `ENV`), indicando de forma interactiva qué pasos se han completado, cuál está activo en este momento (con animación de pulso) y cuáles son futuros.
* **Píldoras Informativas (Pills):** Datos secundarios como fecha de entrega, número de artículos y folios de facturas/entregas representados mediante cápsulas visuales autolimpiables.
* **Estado de Sincronización SAP:** Un badge en la esquina inferior derecha que indica el estado del documento en SAP (`ABIERTO`, `CERRADO`, `CANCELADO`).
* **Micro-animaciones:** Efectos de hover sofisticados (desplazamiento vertical leve y aumento de sombras) y transiciones CSS de alto rendimiento de tipo *ease cubic-bezier*.

---

## 2. Sistema de Diseño (Variables CSS)

Para mantener la estética visual premium (tipografías, colores, esquinas redondeadas y sombras), asegúrate de que tu hoja de estilos principal defina las siguientes variables CSS en el `:root`:

```css
:root {
    /* Colores base */
    --bg: #f0f2f5;
    --surface: #ffffff;
    --text: #1e293b;
    --text-muted: #64748b;
    --text-faint: #94a3b8;
    --border: #e2e8f0;
    --border-light: #f1f5f9;

    /* Bordes y Sombras */
    --radius: 16px;
    --radius-sm: 10px;
    --shadow-card: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03);
    --shadow-hover: 0 4px 16px rgba(0,0,0,0.08);

    /* Tipografías */
    --font: 'Outfit', 'Inter', -apple-system, sans-serif;
    --mono: 'JetBrains Mono', 'Fira Code', monospace;

    /* Transiciones */
    --transition: 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
```

---

## 3. Estructura HTML (Blueprint)

El siguiente fragmento representa el marcado estándar del componente estructurado con soporte para **Alpine.js**:

```html
<!-- Grid de Tarjetas (Contenedor Recomendado) -->
<div class="orders-grid">
    
    <!-- Plantilla de Tarjeta -->
    <div class="order-card" 
         :class="getCardAccentClass(order.status)" 
         @click="toggleExpand(order.order_id, $event)">
        
        <!-- Cabecera de la Tarjeta -->
        <div class="card-top">
            <div class="card-order-id">
                <span class="order-hash">#</span><span x-text="order.order_id">19280</span>
            </div>
            <!-- Opcional: Badge de envejecimiento / criticidad (Aging) -->
            <div class="card-aging aging-ok">
                <svg class="aging-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>&lt; 1h</span>
            </div>
        </div>

        <!-- Información del Cliente -->
        <div class="card-customer">
            <div class="customer-name" x-text="order.customer_name">ALBERTO ROSAS HERNANDEZ</div>
            <div class="customer-id-row">
                <span class="customer-code" x-text="order.customer_code">CL00037</span>
                <template x-if="order.created_by">
                    <span class="customer-seller" x-text="order.created_by">YOLANDA IVETH ZUÑIGA RIOS</span>
                </template>
            </div>
        </div>

        <!-- Línea de Tiempo de Progreso (Stepper) -->
        <div class="progress-timeline">
            <template x-for="(step, si) in statusSteps" :key="step.key">
                <div class="timeline-step" :class="getStepClass(order.status, step.key)">
                    <!-- Círculo indicador -->
                    <div class="step-dot">
                        <template x-if="isStepCompleted(order.status, step.key)">
                            <svg class="step-check" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                            </svg>
                        </template>
                    </div>
                    <!-- Etiqueta del Paso -->
                    <div class="step-label" x-text="step.short"></div>
                    <!-- Conector de pasos -->
                    <div class="step-connector" 
                         x-show="si < statusSteps.length - 1" 
                         :class="isStepCompleted(order.status, step.key) ? 'connector-done' : ''">
                    </div>
                </div>
            </template>
        </div>

        <!-- Pie de la Tarjeta (Footer) -->
        <div class="card-footer">
            <div class="footer-pills">
                <!-- Píldora de Fecha -->
                <div class="pill pill-date" :class="isOverdue(order) ? 'pill-overdue' : ''">
                    <svg class="pill-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <span x-text="formatDate(order.delivery_date)">24/07/2026</span>
                </div>
                <!-- Píldora de Artículos -->
                <div class="pill pill-items">
                    <svg class="pill-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                    </svg>
                    <span x-text="(order.items ? order.items.length : 0) + ' art.'">8 art.</span>
                </div>
            </div>
            
            <!-- Estado SAP -->
            <div class="sap-status" :class="getSapClass(order.sap_status)">
                <span x-text="order.sap_status || 'N/A'">ABIERTO</span>
            </div>
        </div>
    </div>

</div>
```

---

## 4. Estilos Visuales (Hojas de Estilo CSS)

Agrega los siguientes estilos a la hoja de CSS asociada a la vista. Este bloque define la grilla adaptativa, la animación de inserción gradual y los colores de acento dinámicos.

```css
/* Contenedor Adaptativo de Tarjetas */
.orders-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
    align-items: start;
}

/* Tarjeta Principal */
.order-card {
    background: var(--surface);
    border-radius: var(--radius);
    border: 1px solid var(--border-light);
    padding: 20px;
    cursor: pointer;
    transition: var(--transition);
    animation: cardIn 0.3s ease both;
    position: relative;
    overflow: hidden;
}

.order-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    border-radius: 4px 0 0 4px;
    transition: var(--transition);
}

/* Efecto de Hover Premium */
.order-card:hover {
    box-shadow: var(--shadow-hover);
    transform: translateY(-2px);
}

/* Animación de entrada de tarjeta */
@keyframes cardIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Colores de Acento (Borde Izquierdo) */
.accent-amber::before { background: linear-gradient(180deg, #f59e0b, #d97706); }
.accent-violet::before { background: linear-gradient(180deg, #8b5cf6, #7c3aed); }
.accent-sky::before { background: linear-gradient(180deg, #0ea5e9, #0284c7); }
.accent-pink::before { background: linear-gradient(180deg, #ec4899, #db2777); }
.accent-emerald::before { background: linear-gradient(180deg, #10b981, #059669); }
.accent-teal::before { background: linear-gradient(180deg, #14b8a6, #0d9488); }
.accent-blue::before { background: linear-gradient(180deg, #3b82f6, #2563eb); }
.accent-orange::before { background: linear-gradient(180deg, #f97316, #ea580c); }
.accent-red::before { background: linear-gradient(180deg, #ef4444, #b91c1c); }
.accent-slate::before { background: #94a3b8; }

/* Elementos Superiores */
.card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 10px;
}

.card-order-id {
    font-size: 22px;
    font-weight: 800;
    font-family: var(--mono);
    letter-spacing: -0.02em;
    color: var(--text);
}

.order-hash {
    color: var(--text-faint);
    font-weight: 400;
}

/* Envejecimiento del Pedido (Aging Caps) */
.card-aging {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    font-family: var(--mono);
}
.aging-icon { width: 12px; height: 12px; }
.aging-ok { background: #f0fdf4; color: #16a34a; }
.aging-warn { background: #fffbeb; color: #d97706; }
.aging-danger { 
    background: #fef2f2; 
    color: #dc2626; 
    animation: pulse-danger 2s infinite; 
}
@keyframes pulse-danger { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }

/* Cliente y Etiquetas */
.card-customer {
    margin-bottom: 14px;
}

.customer-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.3;
}

.customer-id-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 4px;
    flex-wrap: wrap;
}

.customer-code {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--text-faint);
}

.customer-seller {
    font-size: 10px;
    font-weight: 600;
    color: #6366f1;
    background: #eef2ff;
    padding: 1px 8px;
    border-radius: 4px;
}

/* ==========================================================================
   PROGRESS TIMELINE (STEPPER HORIZONTAL)
   ========================================================================== */
.progress-timeline {
    display: flex;
    align-items: flex-start;
    gap: 0;
    margin-bottom: 14px;
    padding: 8px 0;
}

.timeline-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    position: relative;
    flex: 1;
    min-width: 36px;
}

.step-dot {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 2px solid var(--border);
    background: var(--surface);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: var(--transition);
    position: relative;
    z-index: 2;
    flex-shrink: 0;
}

.step-check {
    width: 9px;
    height: 9px;
    stroke-width: 3;
}

.step-label {
    font-size: 8px;
    font-weight: 700;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-top: 4px;
    text-align: center;
    white-space: nowrap;
}

.step-connector {
    position: absolute;
    top: 8px;
    left: calc(50% + 9px);
    width: calc(100% - 18px);
    height: 2px;
    background: var(--border);
    z-index: 1;
}

/* Estados Dinámicos de los Pasos */

/* Completado */
.step-done .step-dot { background: #10b981; border-color: #10b981; }
.step-done .step-check { color: #fff; }
.step-done .step-label { color: #059669; }
.step-done .step-connector, .connector-done { background: #10b981 !important; }

/* Paso Activo (Pulsante) */
.step-current .step-dot {
    border-color: #6366f1;
    background: #6366f1;
    box-shadow: 0 0 0 4px rgba(99,102,241,0.2);
    animation: pulse-current 2s infinite;
}
.step-current .step-label { color: #4f46e5; font-weight: 700; }
@keyframes pulse-current { 
    0%, 100% { box-shadow: 0 0 0 4px rgba(99,102,241,0.2); } 
    50% { box-shadow: 0 0 0 6px rgba(99,102,241,0.1); } 
}

/* Futuro */
.step-future .step-dot { border-color: var(--border); background: var(--bg); }
.step-future .step-label { color: var(--text-faint); }

/* ==========================================================================
   PIES DE TARJETA Y PÍLDORAS (PILLS)
   ========================================================================== */
.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 10px;
}

.footer-pills {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.pill {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    background: var(--bg);
    color: var(--text-muted);
}

.pill-icon {
    width: 12px;
    height: 12px;
}

.pill-overdue {
    background: #fef2f2;
    color: #dc2626;
}

/* Estado SAP */
.sap-status {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 3px 8px;
    border-radius: 6px;
}

.sap-open { background: #f0fdf4; color: #16a34a; }
.sap-closed { background: #f1f5f9; color: #64748b; }
.sap-cancelled { background: #fef2f2; color: #dc2626; }
```

---

## 5. Lógica del Componente (Javascript/Alpine.js)

Para controlar dinámicamente el progreso, las clases dinámicas de acento y los estados, debes registrar los siguientes métodos en tu componente de Alpine.js:

```javascript
function orderComponent() {
    return {
        // Estructura de pasos del pipeline en el orden deseado
        statusSteps: [
            { key: 'Pendiente', short: 'Pend' },
            { key: 'En Proceso', short: 'Proc' },
            { key: 'Facturacion', short: 'Fact' },
            { key: 'Relacion de envio', short: 'Rel' },
            { key: 'Enviado al cliente', short: 'Env' }
        ],

        // Mapeo numérico secuencial para cálculos de progresión
        get statusIndex() {
            return {
                'Pendiente': 0,
                'En Proceso': 1,
                'Entregado': 1,
                'Preparando': 1,
                'Facturacion': 2,
                'Relacion de envio': 3,
                'Recibido por almacen': 3,
                'Enviado al cliente': 4
            };
        },

        getStepIndex(status) {
            return this.statusIndex[status] ?? -1;
        },

        // Determina si un paso del stepper ya se completó
        isStepCompleted(orderStatus, stepKey) {
            return this.getStepIndex(orderStatus) > this.getStepIndex(stepKey);
        },

        // Determina si un paso del stepper es el paso actual del pedido
        isStepCurrent(orderStatus, stepKey) {
            return orderStatus === stepKey;
        },

        // Retorna la clase CSS correspondiente para cada paso del stepper
        getStepClass(orderStatus, stepKey) {
            if (this.isStepCurrent(orderStatus, stepKey)) return 'step-current';
            if (this.isStepCompleted(orderStatus, stepKey)) return 'step-done';
            return 'step-future';
        },

        // Retorna el acento de color correspondiente para la barra lateral izquierda
        getCardAccentClass(status) {
            const map = {
                'Pendiente': 'accent-amber',
                'En Proceso': 'accent-violet',
                'Entregado': 'accent-sky',
                'Facturacion': 'accent-pink',
                'Relacion de envio': 'accent-emerald',
                'Enviado al cliente': 'accent-teal',
                'En Espera': 'accent-orange',
                'Cancelado': 'accent-red'
            };
            return map[status] || 'accent-slate';
        },

        // Retorna el estilo CSS para el estado de sincronización de SAP
        getSapClass(status) {
            if (status === 'Abierto') return 'sap-open';
            if (status === 'Cerrado') return 'sap-closed';
            if (status === 'Cancelado') return 'sap-cancelled';
            return '';
        },

        // Determina si la entrega del pedido está retrasada
        isOverdue(order) {
            if (!order.delivery_date) return false;
            const d = new Date(order.delivery_date);
            if (isNaN(d)) return false;
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            return d < today;
        },

        // Opcional: Formatea fechas amigables
        formatDate(dateString) {
            if (!dateString) return '';
            const d = new Date(dateString);
            if (isNaN(d)) return dateString;
            return d.toLocaleDateString('es-MX', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric'
            });
        }
    };
}
```

---

## 6. Instrucciones para Reutilización Rápida

1. **Importa las Fuentes:** Asegúrate de incluir las tipografías modernas `Outfit` y `JetBrains Mono` en el `<head>` de tu documento:
   ```html
   <link rel="preconnect" href="https://fonts.googleapis.com">
   <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
   <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
   ```
2. **Copia los Estilos CSS:** Agrega las variables `:root` e integra el bloque de estilos del componente en tu archivo `.css`.
3. **Prepara el Script de Datos:** Copia e integra las funciones de Javascript de la sección 5 en la inicialización de tu aplicación (por ejemplo en `x-data`).
4. **Inserta el Marcado HTML:** Utiliza la estructura HTML de la sección 3 ajustando los nombres de atributos (`order.order_id`, `order.status`, etc.) a los de tu nuevo backend o modelo de datos.

---
*Graph Context: Regresar a [[Home]] (Arquitectura)*
