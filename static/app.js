// State Management
let currentUser = null;
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

// SaaS UI elements
const loginContainer = document.getElementById("login-container");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const appContainer = document.getElementById("app-container");
const btnLogout = document.getElementById("btn-logout");
const navUserInfo = document.getElementById("nav-user-info");
const navUsername = document.getElementById("nav-username");
const navCompanyName = document.getElementById("nav-company-name");

const navDashboard = document.getElementById("nav-dashboard");
const navHistory = document.getElementById("nav-history");
const navAdministration = document.getElementById("nav-administration");

const dashboardSection = document.getElementById("dashboard-section");
const administrationSection = document.getElementById("administration-section");
const heroSection = document.getElementById("hero-section");
const historySection = document.getElementById("history");

const createCompanyForm = document.getElementById("create-company-form");
const createCompanyError = document.getElementById("create-company-error");
const createCompanySuccess = document.getElementById("create-company-success");
const companiesTableBody = document.getElementById("companies-table-body");

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
    checkAuth();
    setupTheme();
    setupEventListeners();
});

// Event Listeners Setup
function setupEventListeners() {
    scrapeForm.addEventListener("submit", handleFormSubmit);
    btnStop.addEventListener("click", handleStopClick);
    
    // Auth Forms
    loginForm.addEventListener("submit", handleLoginFormSubmit);
    btnLogout.addEventListener("click", handleLogoutClick);
    
    // SuperAdmin Forms
    createCompanyForm.addEventListener("submit", handleCreateCompanySubmit);
    
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
    
    // Tabs Navigation
    navDashboard.addEventListener("click", (e) => {
        e.preventDefault();
        showTab("dashboard");
    });
    
    navHistory.addEventListener("click", (e) => {
        e.preventDefault();
        showTab("dashboard");
        setTimeout(() => {
            historySection.scrollIntoView({ behavior: "smooth" });
        }, 100);
    });
    
    navAdministration.addEventListener("click", (e) => {
        e.preventDefault();
        showTab("admin");
    });
}

// Navigation Tab switcher
function showTab(tab) {
    if (tab === "dashboard") {
        navDashboard.classList.add("active");
        navHistory.classList.remove("active");
        navAdministration.classList.remove("active");
        
        dashboardSection.style.display = "grid";
        heroSection.style.display = "block";
        administrationSection.style.display = "none";
        historySection.style.display = "block";
    } else if (tab === "admin") {
        navAdministration.classList.add("active");
        navDashboard.classList.remove("active");
        navHistory.classList.remove("active");
        
        dashboardSection.style.display = "none";
        heroSection.style.display = "none";
        administrationSection.style.display = "block";
        historySection.style.display = "none";
        resultsContainer.style.display = "none";
        
        loadCompanies();
    }
}

// Check Authentication Status
async function checkAuth() {
    try {
        const res = await fetch("/api/me");
        if (res.status === 401) {
            showLoginView();
            return;
        }
        if (!res.ok) throw new Error("Auth status validation failed");
        
        currentUser = await res.json();
        setupUserDashboard(currentUser);
    } catch (err) {
        showLoginView();
    }
}

// Show Login overlay view
function showLoginView() {
    currentUser = null;
    loginContainer.style.display = "flex";
    appContainer.style.display = "none";
    loginError.style.display = "none";
    loginError.textContent = "";
}

// Show Dashboard view
function setupUserDashboard(user) {
    loginContainer.style.display = "none";
    appContainer.style.display = "block";
    
    // Set user metadata badges
    navUsername.textContent = user.username;
    navCompanyName.textContent = user.company_name || (user.role === "superadmin" ? "SaaS Root" : "Tenancy");
    navUserInfo.style.display = "inline-flex";
    
    // SuperAdmin view controls
    if (user.role === "superadmin") {
        navAdministration.style.display = "inline-block";
        document.querySelectorAll(".col-company").forEach(el => el.style.display = "table-cell");
        document.getElementById("hero-company-badge").textContent = "SAAS CENTRAL PLATFORM";
        document.getElementById("hero-title-text").textContent = "SuperAdmin Data Control Center";
        document.getElementById("results-subtitle").textContent = "Mirrored product results from all companies.";
    } else {
        navAdministration.style.display = "none";
        document.querySelectorAll(".col-company").forEach(el => el.style.display = "none");
        document.getElementById("hero-company-badge").textContent = `TENANT CONSOLE - ${user.company_name.toUpperCase()}`;
        document.getElementById("hero-title-text").textContent = "Execute Custom Product Crawls";
        document.getElementById("results-subtitle").textContent = "Top matching laptops crawled under your tenancy.";
    }
    
    // Reset view
    showTab("dashboard");
    loadHistory();
}

// Handle Login request
async function handleLoginFormSubmit(e) {
    e.preventDefault();
    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value.trim();
    
    loginError.style.display = "none";
    loginError.textContent = "";
    
    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Authentication credentials rejected");
        }
        
        document.getElementById("login-username").value = "";
        document.getElementById("login-password").value = "";
        await checkAuth();
    } catch (err) {
        loginError.textContent = err.message;
        loginError.style.display = "block";
    }
}

// Handle Logout request
async function handleLogoutClick() {
    try {
        await fetch("/api/auth/logout", { method: "POST" });
        showLoginView();
    } catch (err) {
        console.error("Logout failed:", err);
    }
}

// Handle Admin provisioning request
async function handleCreateCompanySubmit(e) {
    e.preventDefault();
    const company_name = document.getElementById("new-company-name").value.trim();
    const username = document.getElementById("new-username").value.trim();
    const password = document.getElementById("new-password").value.trim();
    
    createCompanyError.style.display = "none";
    createCompanySuccess.style.display = "none";
    
    try {
        const res = await fetch("/api/superadmin/companies", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_name, username, password })
        });
        
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Failed to provision new company");
        }
        
        const data = await res.json();
        createCompanySuccess.textContent = data.message;
        createCompanySuccess.style.display = "block";
        
        document.getElementById("new-company-name").value = "";
        document.getElementById("new-username").value = "";
        document.getElementById("new-password").value = "";
        
        loadCompanies();
    } catch (err) {
        createCompanyError.textContent = err.message;
        createCompanyError.style.display = "block";
    }
}

// Load tenancies list
async function loadCompanies() {
    try {
        const res = await fetch("/api/superadmin/companies");
        if (!res.ok) throw new Error("Failed to load tenancies");
        
        const companies = await res.json();
        companiesTableBody.innerHTML = "";
        
        if (companies.length === 0) {
            companiesTableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--mute);">No active tenancies provisioned yet.</td></tr>`;
            return;
        }
        
        companies.forEach(comp => {
            const tr = document.createElement("tr");
            const dateStr = new Date(comp.created_at).toLocaleString();
            
            tr.innerHTML = `
                <td><strong>${comp.company_name}</strong></td>
                <td><code>${comp.username}</code></td>
                <td><code>${comp.db_name}.db</code></td>
                <td>${dateStr}</td>
            `;
            companiesTableBody.appendChild(tr);
        });
    } catch (err) {
        console.error("Load companies error:", err);
    }
}

// Theme Management
function setupTheme() {
    const btnTheme = document.getElementById("btn-theme-toggle");
    
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
        const match = message.match(/\[(\d+)\/(\d+)\]/);
        if (match) {
            const current = parseInt(match[1]);
            const total = parseInt(match[2]);
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
    
    let attempts = 0;
    const maxAttempts = 10;
    const pollInterval = 1500;
    
    async function fetchResults() {
        try {
            const response = await fetch(`/api/results/${jobId}`);
            if (!response.ok) throw new Error("Failed to fetch results");
            
            const data = await response.json();
            
            if (data.status === "completed") {
                activeResults = data.products;
                renderResults(activeResults);
                addLogLine(`Successfully loaded ${activeResults.length} scraped products to table view.`, "success");
                cleanupUI();
            } else if (data.status === "failed" || data.status === "stopped") {
                addLogLine(`Job ended with status: ${data.status}. Reason: ${data.error_message || 'Unknown error'}`, "error");
                cleanupUI();
            } else {
                attempts++;
                if (attempts < maxAttempts) {
                    setTimeout(fetchResults, pollInterval);
                } else {
                    addLogLine(`Job ended with status: ${data.status}. Reason: Task execution timed out.`, "error");
                    cleanupUI();
                }
            }
        } catch (err) {
            addLogLine(`Error fetching results: ${err.message}`, "error");
            cleanupUI();
        }
    }
    
    function cleanupUI() {
        toggleInputs(false);
        setRunnerStatus("idle");
        btnStop.style.display = "none";
        btnSubmit.style.display = "flex";
        loadHistory();
    }
    
    fetchResults();
}

// Render Results Table
function renderResults(products) {
    resultsTableBody.innerHTML = "";
    
    const showCompanyCol = currentUser && currentUser.role === "superadmin";
    
    if (products.length === 0) {
        const colSpan = showCompanyCol ? 8 : 7;
        resultsTableBody.innerHTML = `<tr><td colspan="${colSpan}" style="text-align: center; color: var(--mute);">No products scraped. Verify your website inputs and element selectors.</td></tr>`;
        resultsContainer.style.display = "block";
        return;
    }
    
    products.forEach((product, idx) => {
        const tr = document.createElement("tr");
        
        const thumbnailSrc = product.image_url || "https://placehold.co/100x100?text=No+Image";
        
        tr.innerHTML = `
            <td><img src="${thumbnailSrc}" class="table-thumbnail" alt="${product.title}"></td>
            ${showCompanyCol ? `<td><span class="user-badge-premium">${product.company_name || 'N/A'}</span></td>` : ''}
            <td><strong>${product.brand || 'Unknown'}</strong></td>
            <td><div class="table-title" title="${product.title}">${product.title}</div></td>
            <td><strong>${product.price || 'N/A'}</strong></td>
            <td><i class="fa-solid fa-star" style="color: var(--warning);"></i> ${parseRating(product.rating)}</td>
            <td><span style="color: var(--mute);">${product.reviews_count || '0'}</span></td>
            <td><button class="button-secondary-sm btn-view-details" data-idx="${idx}">View Details</button></td>
        `;
        resultsTableBody.appendChild(tr);
    });
    
    document.querySelectorAll(".btn-view-details").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const idx = parseInt(e.currentTarget.dataset.idx);
            openDetailsModal(products[idx]);
        });
    });
    
    resultsContainer.style.display = "block";
    resultsContainer.scrollIntoView({ behavior: 'smooth' });
}

// Parse ratings
function parseRating(ratingStr) {
    if (!ratingStr) return "N/A";
    const match = ratingStr.match(/(\d+\.\d+|\d+)/);
    return match ? match[1] : ratingStr;
}

// Render Past History Grid
async function loadHistory() {
    try {
        const response = await fetch("/api/history");
        if (response.status === 401) return; // Ignore if called during logout
        if (!response.ok) throw new Error("Failed to fetch history");
        
        const jobs = await response.json();
        historyTableBody.innerHTML = "";
        
        const showCompanyCol = currentUser && currentUser.role === "superadmin";
        
        if (jobs.length === 0) {
            const colSpan = showCompanyCol ? 8 : 7;
            historyTableBody.innerHTML = `<tr><td colspan="${colSpan}" style="text-align: center; color: var(--mute);">No historical scraping runs found.</td></tr>`;
            return;
        }
        
        jobs.forEach(job => {
            const tr = document.createElement("tr");
            const dateStr = new Date(job.created_at).toLocaleString();
            
            tr.innerHTML = `
                <td style="font-family: var(--font-mono); font-size: 12px;">${job.id.substring(0, 8)}...</td>
                <td>${dateStr}</td>
                ${showCompanyCol ? `<td><span class="user-badge-premium">${job.company_name || 'N/A'}</span></td>` : ''}
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
    
    document.getElementById("modal-product-seller").textContent = product.seller || "Unknown";
    document.getElementById("modal-product-warranty").textContent = product.warranty || "N/A";
    
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
    
    if (product.description) {
        modalDescContainer.style.display = "block";
        modalDesc.textContent = product.description;
    } else {
        modalDescContainer.style.display = "none";
    }

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
