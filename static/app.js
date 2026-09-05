let currentInventoryData = [];

document.addEventListener("DOMContentLoaded", () => {
    loadDashboardData();
});

async function loadDashboardData() {
    const storeId = document.getElementById("storeSelect").value;
    const queryParam = storeId ? `?store_id=${storeId}` : "";

    try {
        // 1. Fetch KPIs
        const kpiRes = await fetch(`/api/dashboard${queryParam}`);
        const kpiData = await kpiRes.json();

        document.getElementById("kpiRevenue").textContent = `$${kpiData.total_revenue_90d.toLocaleString()}`;
        document.getElementById("kpiUnits").textContent = `${kpiData.total_units_sold_90d.toLocaleString()} units sold (90d)`;
        document.getElementById("kpiStockouts").textContent = kpiData.stockout_alerts;
        document.getElementById("kpiDeadStock").textContent = `$${kpiData.inventory_cost_value ? (kpiData.inventory_cost_value * 0.15).toFixed(0) : 0}`;
        document.getElementById("kpiDeadCount").textContent = `${kpiData.dead_stock_alerts} dead stock alerts`;
        document.getElementById("kpiInventoryCost").textContent = `$${kpiData.inventory_cost_value.toLocaleString()}`;
        document.getElementById("kpiSkus").textContent = `${kpiData.total_skus} SKUs in network`;

        // 2. Fetch Alerts Feed
        const alertRes = await fetch(`/api/alerts${queryParam}`);
        const alertData = await alertRes.json();
        renderAttentionFeed(alertData.attention_feed);

        // 3. Fetch Inventory Matrix
        const invRes = await fetch(`/api/inventory${queryParam}`);
        const invData = await invRes.json();
        currentInventoryData = invData.inventory;
        renderInventoryTable(currentInventoryData);

    } catch (err) {
        console.error("Error loading dashboard data:", err);
    }
}

function renderAttentionFeed(alerts) {
    const container = document.getElementById("attentionFeed");
    const countBadge = document.getElementById("alertCountBadge");
    
    countBadge.textContent = `${alerts.length} Flags Today`;
    
    if (!alerts || alerts.length === 0) {
        container.innerHTML = `
            <div class="alert-card MEDIUM" style="text-align: center; color: var(--text-muted);">
                🎉 No critical stock issues detected today! Everything is operating within healthy parameters.
            </div>
        `;
        return;
    }

    container.innerHTML = alerts.map(alert => {
        const assumptionsPretty = JSON.stringify(alert.data_assumptions, null, 2);
        return `
            <div class="alert-card ${alert.severity}">
                <div class="alert-header">
                    <span class="alert-type-badge ${alert.alert_type}">${alert.alert_type.replace("_", " ")}</span>
                    <span class="store-name-tag">🏬 ${alert.store_name}</span>
                </div>
                <div class="alert-title">${alert.product_name} <span style="font-size: 0.8rem; color: var(--text-muted);">(${alert.sku})</span></div>
                <div class="alert-msg">${alert.message}</div>
                <div class="action-box">
                    <div class="action-title">💡 Recommended Action:</div>
                    <div>${alert.recommended_action}</div>
                </div>
                <details>
                    <summary>🔍 View Data & Assumptions Audit Trail</summary>
                    <pre class="assumptions-json">${assumptionsPretty}</pre>
                </details>
            </div>
        `;
    }).join("");
}

function renderInventoryTable(items) {
    const tbody = document.getElementById("inventoryTableBody");
    if (!items || items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color: var(--text-muted);">No inventory records found.</td></tr>`;
        return;
    }

    tbody.innerHTML = items.map(item => {
        const isLow = item.current_stock <= item.reorder_point;
        const statusBadge = isLow 
            ? `<span class="badge-status risk">Low Stock (${item.current_stock})</span>`
            : `<span class="badge-status healthy">Optimal</span>`;

        return `
            <tr>
                <td><strong>${item.store_name}</strong></td>
                <td>${item.product_name}</td>
                <td><code style="color: #93c5fd;">${item.sku}</code></td>
                <td>${item.category}</td>
                <td><strong>${item.current_stock}</strong></td>
                <td>${item.reorder_point}</td>
                <td>${item.lead_time_days} days</td>
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

    // 1. Append User Message
    const userMsgDiv = document.createElement("div");
    userMsgDiv.className = "chat-message user";
    userMsgDiv.innerHTML = `
        <div class="avatar">👤</div>
        <div class="message-content">${escapeHtml(query)}</div>
    `;
    chatHistory.appendChild(userMsgDiv);
    inputEl.value = "";
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // 2. Append Loading Bot Message
    const botMsgDiv = document.createElement("div");
    botMsgDiv.className = "chat-message bot";
    botMsgDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="message-content">
            <span class="loading-dots">Querying inventory data & synthesizing with Gemini...</span>
        </div>
    `;
    chatHistory.appendChild(botMsgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query, store_id: storeId })
        });
        const data = await res.json();

        // Format bot answer with basic Markdown parsing
        const formattedAnswer = formatMarkdown(data.answer);
        botMsgDiv.querySelector(".message-content").innerHTML = `
            ${formattedAnswer}
            <div style="margin-top: 10px; font-size: 0.75rem; color: var(--text-dim); border-top: 1px solid var(--border-color); padding-top: 6px;">
                ⚡ <strong>Grounded Engine:</strong> ${data.source}
            </div>
        `;
    } catch (err) {
        botMsgDiv.querySelector(".message-content").innerHTML = `
            ⚠️ Sorry, an error occurred while connecting to the copilot backend.
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
        .replace(/`([^`]+)`/g, '<code style="background: var(--bg-input); padding: 2px 6px; border-radius: 4px;">$1</code>')
        .replace(/\n- (.*)/g, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    if (html.includes('<li>')) {
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    }
    return `<p>${html}</p>`;
}
