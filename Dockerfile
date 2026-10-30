FROM python:3.10-slim

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Memory allocation tuning for 512MB RAM containers
ENV MALLOC_ARENA_MAX=2
ENV MALLOC_TRIM_THRESHOLD_=100000

# Prevent Selenium Manager from trying to download browser binaries over the network at runtime
ENV SE_AVOID_BROWSER_DOWNLOAD=true

# Firefox ESR container stability — prevents "Failed to read marionette port" errors
ENV MOZ_HEADLESS=1
ENV MOZ_CRASHREPORTER_DISABLE=1
ENV MOZ_DISABLE_CONTENT_SANDBOX=1

# Install system dependencies, including libraries required by headless Chrome and Firefox ESR
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    unzip \
    tar \
    bzip2 \
    ca-certificates \
    firefox-esr \
    dbus \
    libnss3 \
    libnspr4 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libpango-1.0-0 \
    fonts-liberation \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxtst6 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Ensure /dev/shm exists and /tmp is writable (required by Firefox ESR for marionette IPC)
RUN mkdir -p /dev/shm /tmp/mozilla && chmod 1777 /dev/shm /tmp /tmp/mozilla

# Download and install Geckodriver for Firefox ESR (Primary lightweight browser)
RUN GECKODRIVER_VERSION=v0.35.0 && \
    echo "Installing Geckodriver version: $GECKODRIVER_VERSION" && \
    curl -sSL "https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-linux64.tar.gz" -o /tmp/geckodriver.tar.gz && \
    tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin/ && \
    ln -s /usr/local/bin/geckodriver /usr/bin/geckodriver && \
    chmod +x /usr/local/bin/geckodriver /usr/bin/geckodriver && \
    rm -f /tmp/geckodriver.tar.gz

# Download and install matched Chrome for Testing and ChromeDriver (Fallback browser)
RUN LATEST_RELEASE=$(curl -s https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE) && \
    echo "Installing Chrome for Testing and ChromeDriver version: $LATEST_RELEASE" && \
    curl -sSL "https://storage.googleapis.com/chrome-for-testing-public/${LATEST_RELEASE}/linux64/chrome-linux64.zip" -o /tmp/chrome-linux64.zip && \
    unzip -q /tmp/chrome-linux64.zip -d /opt && \
    ln -s /opt/chrome-linux64/chrome /usr/bin/google-chrome && \
    ln -s /opt/chrome-linux64/chrome /usr/bin/chrome && \
    curl -sSL "https://storage.googleapis.com/chrome-for-testing-public/${LATEST_RELEASE}/linux64/chromedriver-linux64.zip" -o /tmp/chromedriver-linux64.zip && \
    unzip -q /tmp/chromedriver-linux64.zip -d /opt && \
    ln -s /opt/chromedriver-linux64/chromedriver /usr/bin/chromedriver && \
    chmod +x /opt/chrome-linux64/chrome /opt/chromedriver-linux64/chromedriver /usr/bin/google-chrome /usr/bin/chromedriver && \
    rm -f /tmp/chrome-linux64.zip /tmp/chromedriver-linux64.zip

# Verify Firefox ESR, Geckodriver, Chrome, and ChromeDriver installations
RUN firefox-esr --version && geckodriver --version && google-chrome --version && chromedriver --version

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create Directories for Databases and static files and set permissions
RUN mkdir -p Databases static && chmod -R 777 Databases static

# Set TMPDIR for Firefox profile creation in cloud environments
ENV TMPDIR=/tmp/mozilla

# Cloud environments (Railway, Blitz, Render) provide PORT
EXPOSE 8000

# Start FastAPI server using Uvicorn
# The dbus-daemon init prevents Firefox "Failed to open connection" IPC warnings
CMD ["sh", "-c", "mkdir -p /dev/shm /tmp/mozilla && chmod 1777 /dev/shm /tmp/mozilla 2>/dev/null; dbus-daemon --system --nofork &>/dev/null & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
