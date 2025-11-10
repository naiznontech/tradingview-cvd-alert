FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV DISPLAY=:99

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 10000

CMD ["python", "-u", "main.py"]
```

### **File 3: `main.py`**
- Đã có từ artifact trước
- Nhớ sửa 3 dòng config

---

## ✅ **SAU KHI TẠO LẠI DOCKERFILE:**

1. **Quay lại Render**
2. Click **"Manual Deploy"** → **"Clear build cache & deploy"**
3. Đợi build (~5-7 phút)

---

## 📊 **LOGS THÀNH CÔNG SẼ HIỂN THỊ:**
```
Step 1/10 : FROM python:3.9-slim
Step 2/10 : RUN apt-get update...
Step 6/10 : COPY requirements.txt .
Step 7/10 : RUN pip install --no-cache-dir -r requirements.txt
---> Running in abc123
Collecting selenium==4.15.2
Collecting pillow==10.1.0
Collecting pytesseract==0.3.10
Collecting requests==2.31.0
Collecting flask==3.0.0  ← PHẢI CÓ DÒNG NÀY
Successfully installed selenium-4.15.2 pillow-10.1.0 pytesseract-0.3.10 requests-2.31.0 flask-3.0.0
---> abc456
Step 8/10 : COPY main.py .
Step 9/10 : EXPOSE 10000
Step 10/10 : CMD ["python", "-u", "main.py"]
==> Build successful!
==> Deploying...
Web server started on port 10000
==================================================
TradingView CVD Alert Bot Started!
==================================================
