// State Management
let activeJobId = null;
let activeResults = [];

// DOM Elements
const scrapeForm = document.getElementById("scrape-form");
const inputWebsite = document.getElementById("input-website");
const inputSearch = document.getElementById("input-search");
const inputLimit = document.getElementById("input-limit");
const inputHeadless = document.getElementById("input-headless");
const btnSubmit = document.getElementById("btn-submit");
const btnStop = document.getElementById("btn-stop");
const terminalLogs = document.getElementById("terminal-logs");
const progressBar = document.getElementById("progress-bar");
const runnerStatus = document.getElementById("runner-status");
const resultsContainer = document.getElementById("results-container");
const resultsTableBody = document.getElementById("results-table-body");
const historyTableBody = document.getElementById("history-table-body");

// Modal Elements
const detailsModal = document.getElementById("details-modal");
const modalOverlay = document.querySelector(".modal-overlay");
const modalCloseBtn = document.getElementById("btn-close-modal");
const modalBrand = document.getElementById("modal-product-brand");
const modalTitle = document.getElementById("modal-product-title");
const modalImage = document.getElementById("modal-product-image");
const modalPrice = document.getElementById("modal-product-price");
const modalRating = document.getElementById("modal-product-rating");
const modalReviews = document.getElementById("modal-product-reviews");
const modalLink = document.getElementById("modal-product-link");
const modalSpecs = document.getElementById("modal-product-specs");
const modalAbout = document.getElementById("modal-product-about");
const modalDesc = document.getElementById("modal-product-desc");
const modalDescContainer = document.getElementById("modal-desc-container");

// Export buttons
const btnExportCsv = document.getElementById("btn-export-csv");
const btnExportJson = document.getElementById("btn-export-json");

// Init application
document.addEventListener("DOMContentLoaded", () => {
    loadHistory();
    setupTheme();
    setupEventListeners();
});

// Event Listeners Setup
function setupEventListeners() {
    scrapeForm.addEventListener("submit", handleFormSubmit);
    btnStop.addEventListener("click", handleStopClick);
    
    // Presets
    document.querySelectorAll(".preset-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const dataset = e.currentTarget.dataset;
            inputWebsite.value = dataset.site;
            inputSearch.value = dataset.query;
            inputLimit.value = dataset.limit;
        });
    });

    // Modal Close
    modalCloseBtn.addEventListener("click", closeModal);
    modalOverlay.addEventListener("click", closeModal);
    
    // Escape key closes modal
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeModal();
    });

    // Exports
    btnExportCsv.addEventListener("click", () => {
        if (activeJobId) {
            window.location.href = `/api/export/${activeJobId}/csv`;
        }
    });
    btnExportJson.addEventListener("click", () => {
        if (activeJobId) {
            window.location.href = `/api/export/${activeJobId}/json`;
        }
    });
}

// Theme Management
function setupTheme() {
    const btnTheme = document.getElementById("btn-theme-toggle");
    
    // Check saved theme or system preference
    const savedTheme = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    
    if (savedTheme) {
        document.documentElement.setAttribute("data-theme", savedTheme);
        updateThemeButton(savedTheme);
    } else {
        const theme = prefersDark ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", theme);
        updateThemeButton(theme);
    }

    btnTheme.addEventListener("click", () => {
        const currentTheme = document.documentElement.getAttribute("data-theme");
        const nextTheme = currentTheme === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", nextTheme);
        localStorage.setItem("theme", nextTheme);
        updateThemeButton(nextTheme);
    });
}

function updateThemeButton(theme) {
    const btnTheme = document.getElementById("btn-theme-toggle");
    if (theme === "dark") {
        btnTheme.innerHTML = '<i class="fa-solid fa-moon"></i> Dark Mode';
    } else {
        btnTheme.innerHTML = '<i class="fa-solid fa-sun"></i> Light Mode';
    }
}

// Start Scraper Job
async function handleFormSubmit(e) {
    e.preventDefault();
    
    const website = inputWebsite.value.trim();
    const search_query = inputSearch.value.trim();
    const limit = parseInt(inputLimit.value);
    const headless = inputHeadless.checked;
    
    // Reset layout
    terminalLogs.innerHTML = "";
    progressBar.style.width = "0%";
    resultsContainer.style.display = "none";
    
    // Disable inputs
    toggleInputs(true);
    setRunnerStatus("running");
    
    // Toggle buttons
    btnSubmit.style.display = "none";
    btnStop.style.display = "flex";
    btnStop.disabled = false;
    btnStop.innerHTML = '<span>Stop Scraping</span> <i class="fa-solid fa-stop"></i>';
    
    addLogLine("Starting background scrape job registration...", "info");
    
    try {
        const response = await fetch("/api/scrape", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ website, search_query, limit, headless })
        });
        
        if (!response.ok) throw new Error("Failed to register scrape job");
        
        const data = await response.json();
        const job_id = data.job_id;
        activeJobId = job_id;
        
        addLogLine(`Job registered with ID: ${job_id}`, "success");
        
        // Start streaming logs
        connectLogsSSE(job_id, limit);
        
    } catch (err) {
        addLogLine(`Error submitting job: ${err.message}`, "error");
        toggleInputs(false);
        setRunnerStatus("idle");
        btnStop.style.display = "none";
        btnSubmit.style.display = "flex";
    }
}

// Handle Stop Scraping Action
async function handleStopClick() {
    if (!activeJobId) return;
    
    btnStop.disabled = true;
    btnStop.innerHTML = '<span>Stopping...</span> <i class="fa-solid fa-spinner fa-spin"></i>';
    addLogLine("Requesting task cancellation...", "warning");
    
    try {
        const response = await fetch(`/api/scrape/${activeJobId}/stop`, {
            method: "POST"
        });
        if (!response.ok) {
            throw new Error("Failed to send stop signal");
        }
        addLogLine("Stop signal accepted. Waiting for scraper to terminate cleanly...", "info");
    } catch (err) {
        addLogLine(`Error sending stop command: ${err.message}`, "error");
        btnStop.disabled = false;
        btnStop.innerHTML = '<span>Stop Scraping</span> <i class="fa-solid fa-stop"></i>';
    }
}

// SSE Logging Connection
function connectLogsSSE(jobId, limit) {
    const sse = new EventSource(`/api/logs/${jobId}`);
    
    sse.onmessage = (event) => {
        const message = event.data;
        
        // Parse levels and format
        let level = "info";
        let cleanMsg = message;
        
        if (message.startsWith("FATAL ERROR:") || message.startsWith("Error:")) {
            level = "error";
        } else if (message.startsWith("WARNING:")) {
            level = "warning";
        } else if (message.includes("complete") || message.includes("successfully") || message.includes("Initialized")) {
            level = "success";
        }
        
        addLogLine(cleanMsg, level);
        updateProgressFromLog(cleanMsg, limit);
        
        // Finish condition
        if (cleanMsg.includes("Scraping completed successfully") || cleanMsg.includes("Task terminated due to errors")) {
            sse.close();
            onScrapeComplete(jobId);
        }
    };
    
    sse.onerror = (err) => {
        console.error("SSE Connection Error", err);
        addLogLine("SSE stream interrupted. Checking job status...", "warning");
        sse.close();
        onScrapeComplete(jobId);
    };
}

// Update UI Progress from Logs content
function updateProgressFromLog(message, limit) {
    let percentage = 0;
    const msg = message.toLowerCase();
    
    if (msg.includes("initializing chromedriver")) percentage = 10;
    else if (msg.includes("chromedriver initialized")) percentage = 15;
    else if (msg.includes("navigating to")) percentage = 25;
    else if (msg.includes("entering search query")) percentage = 35;
    else if (msg.includes("submitting search form")) percentage = 45;
    else if (msg.includes("extracting product listings")) percentage = 55;
    else if (msg.includes("selected") && msg.includes("listings")) percentage = 65;
    else if (msg.includes("saving scraped products")) percentage = 90;
    else if (msg.includes("scraping completed")) percentage = 100;
    else {
        // Match detail page progress like "[2/5]"
        const match = message.match(/\[(\d+)\/(\d+)\]/);
        if (match) {
            const current = parseInt(match[1]);
            const total = parseInt(match[2]);
            // Map [1..N] detail pages into the 65% -> 90% range
            percentage = 65 + Math.round((current / total) * 25);
        }
    }
    
    if (percentage > 0) {
        progressBar.style.width = `${percentage}%`;
    }
}

// Scrape Complete handler
async function onScrapeComplete(jobId) {
    addLogLine("Fetching final scraped data payload...", "info");
    
    try {
        const response = await fetch(`/api/results/${jobId}`);
        if (!response.ok) throw new Error("Failed to fetch results");
        
        const data = await response.json();
        
        if (data.status === "completed") {
            activeResults = data.products;
            renderResults(activeResults);
            addLogLine(`Successfully loaded ${activeResults.length} scraped products to table view.`, "success");
        } else {
            addLogLine(`Job ended with status: ${data.status}. Reason: ${data.error_message || 'Unknown error'}`, "error");
        }
        
    } catch (err) {
        addLogLine(`Error fetching results: ${err.message}`, "error");
    } finally {
        toggleInputs(false);
        setRunnerStatus("idle");
        btnStop.style.display = "none";
        btnSubmit.style.display = "flex";
        loadHistory(); // Reload history grid
    }
}

// Render Results Table
function renderResults(products) {
    resultsTableBody.innerHTML = "";
    
    if (products.length === 0) {
        resultsTableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--mute);">No products scraped. Verify your website inputs and element selectors.</td></tr>`;
        resultsContainer.style.display = "block";
        return;
    }
    
    products.forEach((product, idx) => {
        const tr = document.createElement("tr");
        
        const thumbnailSrc = product.image_url || "https://placehold.co/100x100?text=No+Image";
        
        tr.innerHTML = `
            <td><img src="${thumbnailSrc}" class="table-thumbnail" alt="${product.title}"></td>
            <td><strong>${product.brand || 'Unknown'}</strong></td>
            <td><div class="table-title" title="${product.title}">${product.title}</div></td>
            <td><strong>${product.price || 'N/A'}</strong></td>
            <td><i class="fa-solid fa-star" style="color: var(--warning);"></i> ${parseRating(product.rating)}</td>
            <td><span style="color: var(--mute);">${product.reviews_count || '0'}</span></td>
            <td><button class="button-secondary-sm btn-view-details" data-idx="${idx}">View Details</button></td>
        `;
        resultsTableBody.appendChild(tr);
    });
    
    // Add Click Listeners to View Details
    document.querySelectorAll(".btn-view-details").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const idx = parseInt(e.currentTarget.dataset.idx);
            openDetailsModal(products[idx]);
        });
    });
    
    resultsContainer.style.display = "block";
    
    // Scroll to results
    resultsContainer.scrollIntoView({ behavior: 'smooth' });
}

// Parse "4.3 out of 5 stars" to "4.3"
function parseRating(ratingStr) {
    if (!ratingStr) return "N/A";
    const match = ratingStr.match(/(\d+\.\d+|\d+)/);
    return match ? match[1] : ratingStr;
}

// Render Past History Grid
async function loadHistory() {
    try {
        const response = await fetch("/api/history");
        if (!response.ok) throw new Error("Failed to fetch history");
        
        const jobs = await response.json();
        historyTableBody.innerHTML = "";
        
        if (jobs.length === 0) {
            historyTableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--mute);">No historical scraping runs found.</td></tr>`;
            return;
        }
        
        jobs.forEach(job => {
            const tr = document.createElement("tr");
            const dateStr = new Date(job.created_at).toLocaleString();
            
            tr.innerHTML = `
                <td style="font-family: var(--font-mono); font-size: 12px;">${job.id.substring(0, 8)}...</td>
                <td>${dateStr}</td>
                <td>${job.website}</td>
                <td><code>${job.search_query}</code></td>
                <td>${job.limit}</td>
                <td><span class="status-badge ${job.status}">${job.status}</span></td>
                <td>
                    <button class="button-secondary-sm btn-load-history" data-job-id="${job.id}">
                        Load Data
                    </button>
                </td>
            `;
            historyTableBody.appendChild(tr);
        });
        
        // Add Action Click Listeners
        document.querySelectorAll(".btn-load-history").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const jobId = e.currentTarget.dataset.jobId;
                activeJobId = jobId;
                progressBar.style.width = "100%";
                addLogLine(`Loading historical data for job ${jobId}...`, "info");
                
                try {
                    const res = await fetch(`/api/results/${jobId}`);
                    if (!res.ok) throw new Error("Failed to fetch historical data");
                    const data = await res.json();
                    activeResults = data.products;
                    renderResults(activeResults);
                    addLogLine(`Loaded ${activeResults.length} items from DB successfully.`, "success");
                } catch(err) {
                    addLogLine(`Error: ${err.message}`, "error");
                }
            });
        });
        
    } catch(err) {
        console.error("History fetch error:", err);
    }
}

// Modal Detail Drawer Operations
function openDetailsModal(product) {
    modalBrand.textContent = product.brand ? product.brand.toUpperCase() : "UNKNOWN BRAND";
    modalTitle.textContent = product.title;
    modalImage.src = product.image_url || "https://placehold.co/300x300?text=No+Product+Image";
    modalPrice.textContent = product.price || "N/A";
    modalRating.innerHTML = `<i class="fa-solid fa-star"></i> ${product.rating || 'No ratings'}`;
    modalReviews.textContent = product.reviews_count ? `${product.reviews_count}` : 'No customer reviews';
    modalLink.href = product.url;
    
    // Set Seller & Warranty
    document.getElementById("modal-product-seller").textContent = product.seller || "Unknown";
    document.getElementById("modal-product-warranty").textContent = product.warranty || "N/A";
    
    // Specs Render
    modalSpecs.innerHTML = "";
    const specsKeys = Object.keys(product.specifications || {});
    if (specsKeys.length === 0) {
        modalSpecs.innerHTML = `<div style="grid-column: 1/-1; color: var(--mute); font-size: 13px;">No specifications table could be parsed.</div>`;
    } else {
        specsKeys.forEach(key => {
            const row = document.createElement("div");
            row.className = "spec-row";
            row.innerHTML = `
                <span class="spec-name">${key}</span>
                <span class="spec-val">${product.specifications[key]}</span>
            `;
            modalSpecs.appendChild(row);
        });
    }
    
    // About Items Bullet points
    modalAbout.innerHTML = "";
    const bullets = product.about_items || [];
    if (bullets.length === 0) {
        modalAbout.innerHTML = `<li style="color: var(--mute); list-style: none;">No summary points available.</li>`;
    } else {
        bullets.forEach(point => {
            const li = document.createElement("li");
            li.textContent = point;
            modalAbout.appendChild(li);
        });
    }
    
    // Description
    if (product.description) {
        modalDescContainer.style.display = "block";
        modalDesc.textContent = product.description;
    } else {
        modalDescContainer.style.display = "none";
    }

    // Reviews Render
    const modalReviewsList = document.getElementById("modal-product-reviews-list");
    modalReviewsList.innerHTML = "";
    const reviews = product.reviews || [];
    if (reviews.length === 0) {
        modalReviewsList.innerHTML = `<div style="color: var(--mute); font-size: 13px; padding: 8px 0;">No customer reviews could be scraped.</div>`;
    } else {
        reviews.forEach(rev => {
            const div = document.createElement("div");
            div.className = "review-item";
            
            const rVal = rev.rating || "N/A";
            const ratingText = rVal.includes("★") || rVal === "N/A" ? rVal : `${rVal} ★`;
            
            div.innerHTML = `
                <div class="review-header">
                    <span class="review-rating-badge">${ratingText}</span>
                    <span class="review-title">${rev.title || ""}</span>
                </div>
                <div class="review-text">${rev.text || ""}</div>
                <div class="review-meta">
                    <span>By ${rev.author || "Anonymous"}</span>
                    <span>${rev.date || ""}</span>
                </div>
            `;
            modalReviewsList.appendChild(div);
        });
    }
    
    // Show Modal
    detailsModal.classList.add("active");
}

function closeModal() {
    detailsModal.classList.remove("active");
}

// Utilities Helpers
function toggleInputs(disabled) {
    inputWebsite.disabled = disabled;
    inputSearch.disabled = disabled;
    inputLimit.disabled = disabled;
    inputHeadless.disabled = disabled;
    btnSubmit.disabled = disabled;
    
    // Presets badges disabled
    document.querySelectorAll(".preset-btn").forEach(btn => {
        btn.disabled = disabled;
        btn.style.opacity = disabled ? "0.5" : "1";
        btn.style.pointerEvents = disabled ? "none" : "auto";
    });
}

function setRunnerStatus(status) {
    const indicator = runnerStatus.querySelector("span");
    if (status === "running") {
        indicator.className = "status-pulse-running";
        runnerStatus.childNodes[1].nodeValue = " Running";
    } else {
        indicator.className = "status-pulse-idle";
        runnerStatus.childNodes[1].nodeValue = " Idle";
    }
}

function addLogLine(text, level = "info") {
    const line = document.createElement("div");
    line.className = "terminal-log-line";
    
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    
    line.innerHTML = `
        <span class="log-time">[${timeStr}]</span>
        <span class="log-${level}">${escapeHtml(text)}</span>
    `;
    
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}
