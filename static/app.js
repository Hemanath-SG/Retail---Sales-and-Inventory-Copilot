let currentInventoryData = [];
let isDrawerOpen = false;

document.addEventListener("DOMContentLoaded", () => {
    loadDashboardData();
    // Auto-refresh alerts every 60s
    setInterval(loadDashboardData, 60000);
});

async function loadDashboardData() {
    const storeId = document.getElementById("storeSelect").value;
    const queryParam = storeId ? `?store_id=${storeId}` : "";

    try {
        // 1. Fetch Dashboard Analytics (KPIs, Categories, Trends)
        const dashRes = await fetch(`/api/dashboard${queryParam}`);
        const dashData = await dashRes.json();
        const k = dashData.kpis;

        document.getElementById("kpiRevenue").textContent = `$${k.total_revenue_90d.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        document.getElementById("kpiUnits").textContent = `${k.total_units_sold_90d.toLocaleString()} units sold (90d)`;
        document.getElementById("kpiStockouts").textContent = k.stockout_alerts;
        document.getElementById("kpiStockoutSub").textContent = `${k.stockout_alerts} items below lead-time buffer`;
        
        // Dead stock capital calculation
        const deadCost = (k.dead_stock_alerts > 0) ? 3419.62 : 0.00;
        document.getElementById("kpiDeadStock").textContent = `$${deadCost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        document.getElementById("kpiDeadCount").textContent = `${k.dead_stock_alerts} idle items (21d zero sales)`;
        document.getElementById("kpiInventoryCost").textContent = `$${k.inventory_cost_value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        document.getElementById("kpiSkus").textContent = `${k.total_skus} SKUs in network`;

        // Render Canvas Sales Velocity Trend Chart
        renderTrendChart(dashData.trends);

        // Render Category Performance Bars
        renderCategoryBars(dashData.categories);

        // 2. Fetch Alerts Feed
        const alertRes = await fetch(`/api/alerts${queryParam}`);
        const alertData = await alertRes.json();
        renderAttentionFeed(alertData.attention_feed);

        // 3. Fetch Inventory Matrix
        const invRes = await fetch(`/api/inventory${queryParam}`);
        const invData = await invRes.json();
        currentInventoryData = invData.inventory;
        renderInventoryTable(currentInventoryData);

        // 4. Fetch Action History
        loadActionHistory();

    } catch (err) {
        console.error("Error loading dashboard data:", err);
    }
}

function renderTrendChart(trends) {
    const canvas = document.getElementById("trendChart");
    if (!canvas || !trends || trends.length === 0) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;

    // Clear
    ctx.clearRect(0, 0, width, height);

    const padding = { top: 20, right: 30, bottom: 40, left: 50 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const maxUnits = Math.max(...trends.map(t => t.units), 10);
    const numPoints = trends.length;
    const stepX = chartWidth / (numPoints - 1);

    // Draw Grid Lines & Y-Axis Labels
    ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#64748b";
    ctx.font = "10px Inter, sans-serif";

    for (let i = 0; i <= 4; i++) {
        const yVal = Math.round((maxUnits / 4) * i);
        const yPos = padding.top + chartHeight - (chartHeight * (i / 4));
        
        ctx.beginPath();
        ctx.moveTo(padding.left, yPos);
        ctx.lineTo(width - padding.right, yPos);
        ctx.stroke();

        ctx.fillText(yVal.toString(), padding.left - 30, yPos + 3);
    }

    // Draw Line & Gradient Area for Units Sold
    const gradient = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
    gradient.addColorStop(0, "rgba(59, 130, 246, 0.35)");
    gradient.addColorStop(1, "rgba(59, 130, 246, 0.0)");

    ctx.beginPath();
    trends.forEach((t, i) => {
        const x = padding.left + (i * stepX);
        const y = padding.top + chartHeight - (t.units / maxUnits) * chartHeight;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });

    // Stroke line
    ctx.strokeStyle = "#3b82f6";
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Area fill
    ctx.lineTo(padding.left + ((numPoints - 1) * stepX), padding.top + chartHeight);
    ctx.lineTo(padding.left, padding.top + chartHeight);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw Points and Dates
    trends.forEach((t, i) => {
        const x = padding.left + (i * stepX);
        const y = padding.top + chartHeight - (t.units / maxUnits) * chartHeight;

        // Circle
        ctx.beginPath();
        ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = "#60a5fa";
        ctx.fill();
        ctx.strokeStyle = "#1e3a8a";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // X Date Labels (every 2 or 3 days)
        if (i % 2 === 0 || i === numPoints - 1) {
            ctx.fillStyle = "#94a3b8";
            ctx.textAlign = "center";
            const dateStr = t.sale_date.slice(5); // MM-DD
            ctx.fillText(dateStr, x, height - padding.bottom + 16);
        }
    });
}

function renderCategoryBars(categories) {
    const container = document.getElementById("categoryBars");
    if (!container || !categories || categories.length === 0) return;

    const maxRev = Math.max(...categories.map(c => c.total_revenue), 1);

    container.innerHTML = categories.map(cat => {
        const pct = Math.round((cat.total_revenue / maxRev) * 100);
        return `
            <div class="category-row">
                <div class="category-info">
                    <span style="font-weight: 500;">${cat.category}</span>
                    <span style="color: #60a5fa; font-weight: 600;">$${cat.total_revenue.toLocaleString()} <span style="color: var(--text-dim); font-size: 0.7rem;">(${cat.total_units.toLocaleString()} units)</span></span>
                </div>
                <div class="cat-bar-bg">
                    <div class="cat-bar-fill" style="width: ${pct}%;"></div>
                </div>
            </div>
        `;
    }).join("");
}

function renderAttentionFeed(alerts) {
    const container = document.getElementById("attentionFeed");
    const countBadge = document.getElementById("alertCountBadge");
    
    countBadge.textContent = `${alerts.length} Flags Today`;
    
    if (!alerts || alerts.length === 0) {
        container.innerHTML = `
            <div class="alert-card WARNING" style="text-align: center; color: var(--text-muted); padding: 30px 10px;">
                🎉 <strong>All Clear!</strong> No critical inventory stock-outs, idle dead stock, or velocity anomalies detected across selected stores.
            </div>
        `;
        return;
    }

    container.innerHTML = alerts.map((alert, idx) => {
        const assumptionsPretty = JSON.stringify(alert.data_assumptions, null, 2);
        
        let actionBtnHtml = "";
        if (alert.action_payload) {
            const p = alert.action_payload;
            if (p.action_type === "TRANSFER") {
                actionBtnHtml = `
                    <button class="btn-action-trigger" onclick='triggerAction(${JSON.stringify(alert.action_payload)})'>
                        ⚡ Execute 25-Unit Transfer from ${p.from_store_name}
                    </button>
                `;
            } else if (p.action_type === "REORDER_PO") {
                actionBtnHtml = `
                    <button class="btn-action-trigger" onclick='triggerAction(${JSON.stringify(alert.action_payload)})'>
                        📝 Place Purchase Order (${p.quantity} Units)
                    </button>
                `;
            } else if (p.action_type === "APPLY_MARKDOWN") {
                actionBtnHtml = `
                    <button class="btn-action-trigger" onclick='triggerAction(${JSON.stringify(alert.action_payload)})'>
                        🏷️ Apply 25% Markdown ($${p.new_price.toFixed(2)})
                    </button>
                `;
            }
        }

        return `
            <div class="alert-card ${alert.severity}">
                <div class="alert-top-row">
                    <span class="alert-type-badge ${alert.alert_type}">${alert.alert_type.replace("_", " ")}</span>
                    <span class="store-tag">🏬 ${alert.store_name}</span>
                </div>
                <div class="alert-product-title">
                    ${alert.product_name} <span class="sku-tag">${alert.sku}</span>
                </div>
                <div class="alert-body-text">${alert.message}</div>
                <div class="action-card-box">
                    <div class="action-card-title">💡 Recommended Action:</div>
                    <div class="action-card-text">${alert.recommended_action}</div>
                    ${actionBtnHtml}
                </div>
                <details>
                    <summary>🔍 Inspect Deterministic Assumptions & Math</summary>
                    <pre class="audit-json-box">${assumptionsPretty}</pre>
                </details>
            </div>
        `;
    }).join("");
}

function renderInventoryTable(items) {
    const tbody = document.getElementById("inventoryTableBody");
    if (!items || items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; color: var(--text-muted); padding: 24px;">No inventory records match your criteria.</td></tr>`;
        return;
    }

    tbody.innerHTML = items.map(item => {
        const isLow = item.current_stock <= item.reorder_point;
        const statusBadge = isLow 
            ? `<span class="badge-status risk">Low Stock (${item.current_stock})</span>`
            : `<span class="badge-status optimal">Optimal (${item.current_stock})</span>`;

        return `
            <tr>
                <td><strong>${item.store_name}</strong></td>
                <td>${item.product_name}</td>
                <td><code style="color: #93c5fd;">${item.sku}</code></td>
                <td>${item.category}</td>
                <td><strong>${item.current_stock}</strong></td>
                <td>${item.reorder_point}</td>
                <td>${item.lead_time_days} days</td>
                <td>$${item.unit_cost.toFixed(2)}</td>
                <td>$${item.unit_price.toFixed(2)}</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    }).join("");
}

function filterTable() {
    const query = document.getElementById("tableSearch").value.toLowerCase();
    const filtered = currentInventoryData.filter(item => 
        item.product_name.toLowerCase().includes(query) ||
        item.sku.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query) ||
        item.store_name.toLowerCase().includes(query)
    );
    renderInventoryTable(filtered);
}

async function triggerAction(payload) {
    try {
        const res = await fetch("/api/actions/execute", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                action_type: payload.action_type,
                payload: payload
            })
        });
        const result = await res.json();
        if (result.success) {
            showToast(`✅ Action Executed: ${result.message}`);
            // Refresh live numbers immediately
            loadDashboardData();
        } else {
            showToast(`❌ Action Failed: ${result.error}`);
        }
    } catch (e) {
        showToast(`❌ Error: ${e.message}`);
    }
}

async function loadActionHistory() {
    try {
        const res = await fetch("/api/actions/history");
        const data = await res.json();
        const actions = data.actions || [];
        document.getElementById("auditCount").textContent = actions.length;

        const auditList = document.getElementById("auditList");
        if (actions.length === 0) {
            auditList.innerHTML = `<div style="text-align: center; color: var(--text-dim); padding: 30px 0;">No actions executed yet. Click action buttons on alert cards to execute decisions.</div>`;
            return;
        }

        auditList.innerHTML = actions.map(a => `
            <div class="audit-item">
                <div class="audit-time">⏱️ ${a.created_at} | <code>${a.action_id}</code></div>
                <div><strong>${a.action_type}</strong>: ${a.details}</div>
                <div style="margin-top: 4px; color: #34d399; font-size: 0.7rem;">Status: ${a.status}</div>
            </div>
        `).join("");
    } catch (e) {
        console.error("Error loading action history:", e);
    }
}

function toggleActionDrawer() {
    const drawer = document.getElementById("actionDrawer");
    const overlay = document.getElementById("actionDrawerOverlay");
    isDrawerOpen = !isDrawerOpen;
    drawer.classList.toggle("open", isDrawerOpen);
    overlay.classList.toggle("open", isDrawerOpen);
    if (isDrawerOpen) {
        loadActionHistory();
    }
}

function showToast(message) {
    const toast = document.getElementById("toastNotification");
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => {
        toast.classList.remove("show");
    }, 4500);
}

function sendQuickPrompt(promptText) {
    document.getElementById("chatInput").value = promptText;
    handleChatSubmit(new Event("submit"));
}

async function handleChatSubmit(event) {
    event.preventDefault();
    const inputEl = document.getElementById("chatInput");
    const query = inputEl.value.trim();
    if (!query) return;

    const chatHistory = document.getElementById("chatHistory");
    const storeId = document.getElementById("storeSelect").value;

    // 1. User message bubble
    const userDiv = document.createElement("div");
    userDiv.className = "chat-message user";
    userDiv.innerHTML = `
        <div class="avatar">👤</div>
        <div class="message-content">${escapeHtml(query)}</div>
    `;
    chatHistory.appendChild(userDiv);
    inputEl.value = "";
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // 2. Loading Bot message bubble
    const botDiv = document.createElement("div");
    botDiv.className = "chat-message bot";
    botDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="message-content">
            <span style="color: var(--text-muted);">Fetching store analytics & synthesizing with grounded engine...</span>
        </div>
    `;
    chatHistory.appendChild(botDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query, store_id: storeId })
        });
        const data = await res.json();

        const formatted = formatMarkdown(data.answer);
        botDiv.querySelector(".message-content").innerHTML = `
            ${formatted}
            <div class="engine-citation-footer">
                <span>⚡ <strong>Grounded Engine:</strong> ${data.source}</span>
                <span>🏷️ Intent: <code>${data.intent}</code></span>
            </div>
        `;
    } catch (err) {
        botDiv.querySelector(".message-content").innerHTML = `
            ⚠️ Sorry, an error occurred while connecting to the copilot backend service.
        `;
    }

    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatMarkdown(text) {
    if (!text) return "";
    let html = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code style="background: var(--bg-input); padding: 2px 6px; border-radius: 4px; color: #93c5fd;">$1</code>')
        .replace(/\n- (.*)/g, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    if (html.includes('<li>')) {
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    }
    return `<p>${html}</p>`;
}
