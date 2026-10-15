# 🚀 Render Deployment Guide — iSwitch Store Bots

This folder contains the complete, hardened, and verified code for deploying both the **Customer Bot** and **Admin Bot** to [Render](https://render.com).

---

## 📁 Key Files Prepared for Render

| File | Purpose |
| :--- | :--- |
| [`main.py`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/main.py) | Cloud entrypoint; runs dual polling + automatic HTTP healthcheck on `$PORT` |
| [`run.py`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/run.py) | Core runner with resilient error handling and graceful shutdown |
| [`requirements.txt`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/requirements.txt) | Python dependencies (`python-telegram-bot`, `aiosqlite`, `aiohttp`, etc.) |
| [`render.yaml`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/render.yaml) | Render Blueprint for 1-click automatic infrastructure setup |
| [`Procfile`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/Procfile) | Process file defining `web` and `worker` commands |
| [`Dockerfile`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/Dockerfile) | Production container setup if deploying via Docker |
| [`.env.example`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/.env.example) | Reference of all required environment variables |

---

## ⚡ Deployment Methods

### Method 1: Web Service (Free Tier Compatible)

Render offers a Free Tier for **Web Services**. Because we added an automatic internal HTTP health server on `$PORT` in [`run.py`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/run.py), you can deploy on the **Free Plan** without port timeout errors!

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Production release for Render"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
2. **Create New Web Service**:
   - Log into [dashboard.render.com](https://dashboard.render.com).
   - Click **New +** -> **Web Service**.
   - Connect your GitHub repository.
3. **Configure**:
   - **Name**: `iswitch-store-bots`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Health Check Path**: `/health`
4. **Set Environment Variables**:
   - `CUSTOMER_BOT_TOKEN`: Your customer bot token from `@BotFather`
   - `ADMIN_BOT_TOKEN`: Your admin bot token from `@BotFather`
   - `ADMIN_USER_IDS`: `742368838,8798202536`
   - `TELEGRAM_CHANNEL`: `@iSwitch0`
   - `PYTHON_VERSION`: `3.11.9`
5. Click **Deploy Web Service**.

---

### Method 2: One-Click Blueprint (`render.yaml`)

1. Connect your repository under **Blueprints** on Render.
2. Render reads [`render.yaml`](file:///C:/Users/SolNet/.gemini/antigravity-ide/scratch/iswitch_store/render.yaml).
3. Fill in your `CUSTOMER_BOT_TOKEN` and `ADMIN_BOT_TOKEN`.
4. Click **Apply**.

---

## ✅ Deployment Checklist

- [x] Scope / variable bug resolved (`UnboundLocalError` eradicated).
- [x] Zero-crash checkout handler (`_finalize_order` wrapped with fallback).
- [x] Admin product wizard: prompts for **Name**, **Category**, **Condition (New/Used)**, **Stock Quantity**, **Price**, **Specifications**, and **Image**.
- [x] Customer catalog: shows condition, stock count (`🟢 Available (X left)`), specs, and details.
- [x] Cloud healthcheck web server added on `$PORT` (`/health`).
- [x] Database: auto-initializes on startup with WAL mode & indexes.
- [x] Test suite: 20/20 tests passing.
