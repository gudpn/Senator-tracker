FROM python:3.9-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    libx11-6 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libasound2 \
    libgbm1 \
    libdrm2 \
    libxkbcommon0 \
    libxfixes3 \
    libxrandr2 \
    libatspi2.0-0 \
    && apt-get clean

# Install Playwright dependencies and browsers
RUN pip install --no-cache-dir playwright && \
    playwright install && \
    playwright install-deps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY senator-scraper.py .
EXPOSE $PORT
CMD ["/bin/sh", "-c", "uvicorn senator-scraper:app --host 0.0.0.0 --port ${PORT:-10000}"]