# 🛍️ iSwitch Production Telegram Commerce System

A dual-bot Telegram e-commerce and administrative management system built for **iSwitch** (`@iSwitch0`). Features a customer store bot, a whitelisted administrative control bot, a shared persistent SQLite/PostgreSQL database, secure payment receipt validation, real-time delivery tracking, and a channel product importer.

---

## 🏗️ Architecture Overview

```
                        ┌─────────────────────────────────────────┐
                        │          Source Telegram Channel         │
                        │                 @iSwitch0               │
                        └───────────────────┬─────────────────────┘
                                            │
                     ┌──────────────────────┴──────────────────────┐
                     │          Sequential Importer & Parser       │
                     │  - Method A: Telegram Desktop JSON Export   │
                     │  - Method B: Authorized MTProto (Telethon)  │
                     │  - Web-Pagination Channel Synchronization   │
                     └──────────────────────┬──────────────────────┘
                                            │
                                            ▼
                        ┌─────────────────────────────────────────┐
                        │         Shared Database & Storage       │
                        │  - SQLite (WAL Mode) / PostgreSQL       │
                        │  - Secure Receipts & Product Media Store│
                        └─────────────┬─────────────┬─────────────┘
                                      │             │
                ┌─────────────────────┴──┐       ┌──┴─────────────────────┐
                │   Customer Store Bot   │       │   Admin Control Bot    │
                │   - Product Catalog    │       │   - Whitelist Auth     │
                │   - Cart & Checkout    │◄─────►│   - Payment Verification│
                │   - Receipt Upload     │       │   - Delivery Dispatch  │
                │   - Order Tracking     │       │   - Live Sync Progress │
                └────────────────────────┘       └────────────────────────┘
```

---

## 🔒 Security Model

1. **Token Security**: Tokens are **never** hard-coded into source files. All secrets are loaded strictly from environment variables:
   - `CUSTOMER_BOT_TOKEN`
   - `ADMIN_BOT_TOKEN`
2. **Whitelist Authentication**: Admin Bot enforces strict ID verification:
   - `ADMIN_USER_ID_1 = 742368838`
   - `ADMIN_USER_ID_2 = 8798202536`
   - Any other user attempting to execute admin commands is immediately denied access, and the incident is recorded in the `audit_logs` table.
3. **Receipt Validation**: File uploads are strictly validated by MIME type and size (under 10MB; JPG, PNG, PDF only), given UUID filenames to prevent path traversal attacks, and isolated from public URLs.
4. **Non-Hallucination Guarantee**: Channel import engine uses strict pattern recognition for English and Amharic text. Incomplete or ambiguous posts are sent to an **Admin Review Queue** (`Pending Review`) rather than inventing missing prices or specifications.
5. **Deduplication**: Channel posts are indexed on `(source_channel, source_message_id)`. Re-processing an existing post updates the current record without creating duplicates.

---

## 🚀 Quick Start Guide

### 1. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your bot tokens from [@BotFather](https://t.me/BotFather):
```ini
CUSTOMER_BOT_TOKEN=123456789:ABC-DEF_YOUR_CUSTOMER_BOT_TOKEN
ADMIN_BOT_TOKEN=987654321:XYZ-UVW_YOUR_ADMIN_BOT_TOKEN

ADMIN_USER_ID_1=742368838
ADMIN_USER_ID_2=8798202536

TELEGRAM_CHANNEL=@iSwitch0
```

### 2. Run the Bots (Long Polling Mode)
```bash
python run.py
```
Both bots will launch concurrently, initialize the database schema, seed initial categories and settings, and start processing messages.

### 3. Run via Webhooks (Production Mode)
```bash
python run_webhook.py
```

### 4. Run Test Suite
```bash
# Unit & CRUD Tests
python tests/test_database.py

# Channel Parser Tests (English + Amharic)
python tests/test_parser.py

# Channel Importer & Deduplication Tests
python tests/test_importer.py

# End-to-End Acceptance Test
python tests/test_flow.py
```

---

## 📱 Bot Interfaces

### 🛍️ Customer Store Bot
- **Main Menu**: `🛍 Shop All`, `📂 Categories`, `🔥 New Arrivals`, `🏷 Offers`, `🔎 Search`, `🛒 My Cart`, `📦 My Orders`, `📞 Contact Admin`, `ℹ️ Help`
- **Product Card**: High-resolution photos, condition, storage, RAM, color, battery health, original channel link, add to cart / instant buy now buttons.
- **Cart & Checkout**: Multi-item cart, quantity adjustments, stock deduction, address / location capture, payment method selector (Telebirr, CBE, Awash).
- **Receipt Upload**: Instant upload of JPG, PNG, or PDF payment slips with live status updates.
- **Order Tracking**: Real-time status badges (`🟡 Pending`, `💳 Payment Pending`, `✅ Payment Confirmed`, `📦 Preparing`, `🚚 Out for Delivery`, `🎉 Delivered`).

### 🔐 Admin Control Bot
- **Dashboard**: Real database numbers (Total products, sold, available, orders, pending payments, verified payments, total sales, category breakdown).
- **Product Admin**: Add, edit price, edit stock, toggle Available / Sold, feature, new arrival, delete, review queue.
- **Order Admin**: Status filters, customer profiles, payment receipt preview, Approve / Reject with custom reason, driver assignment.
- **Channel Import & Sync Panel**: Start sync, pause, resume, retry failed, cancel, JSON export reader, live progress counter.
- **Deliveries**: Dispatch orders, assign drivers, phone numbers, customer delivery notifications.
- **Broadcast**: Compose announcements, promotions, new arrival alerts with confirmation modal.
- **Audit Logs**: Immutable log of every administrative action (timestamp, admin ID, previous value, new value).
