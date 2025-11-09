FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Set display port to avoid crash
ENV DISPLAY=:99

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Expose port for Render
EXPOSE 10000

# Run the bot
CMD ["python", "-u", "main.py"]
```

### **Bước 3: Commit changes**
1. Scroll xuống
2. Commit message: `Fix Chrome installation`
3. Click **"Commit changes"**

---

## ✅ **SAU KHI COMMIT:**

1. **Quay lại Render**
2. Render sẽ **tự động re-deploy** (~2-3 phút)
3. Hoặc click **"Manual Deploy"** → **"Deploy latest commit"**

---

## 📊 **THEO DÕI BUILD MỚI:**

Logs sẽ hiển thị:
```
==> Building...
Step 1/11 : FROM python:3.9-slim
Step 2/11 : RUN apt-get update && apt-get install -y chromium...
---> Running in abc123
Installing chromium...
Installing chromium-driver...
Installing tesseract-ocr...
✅ Successfully installed!
