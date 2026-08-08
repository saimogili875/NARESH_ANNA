# Sri NRI Junior College — WhatsApp Batch Size & Error Alerting System

This document outlines the centralized batch configuration and error logging system implemented for **Sri NRI Junior College** WhatsApp automation.

---

## 🛠️ Summary of Changes Implemented

### 1. Centralized Batch Size Configuration (`WHATSAPP_BATCH_SIZE = 50`)
- Defined `WHATSAPP_BATCH_SIZE = 50` in `core/settings.py`.
- Updated the management command (`send_pending_whatsapp.py`) argument default to read from `settings.WHATSAPP_BATCH_SIZE`.
- Updated all callers to read from `settings.WHATSAPP_BATCH_SIZE`:
  - Webhook view: `/whatsapp/trigger-batch/` (`whatsapp/views.py`)
  - UI background sender: `/attendance/trigger-whatsapp-sender/` (`attendance/views.py`)
  - Absent alerts enqueue flow: `/attendance/send-section-absent/` (`attendance/views.py`)
  - Faculty attendance alerts flow: `/faculty/attendance/` (`faculty/views.py`)

---

### 2. Error Alerting & Persistent File Logging

#### Log File Location:
- **Log Path**: `logs/whatsapp_sender.log` (located inside project root `BASE_DIR`).
- **Rotation Configuration**: `RotatingFileHandler` with 5MB max size per file and 3 backups.
- **Log Format**: `[YYYY-MM-DD HH:MM:SS] [LEVEL] [whatsapp_sender]: message`
- **Logged Events**:
  - `ERROR`: Logged on every failed WhatsApp message attempt with recipient name, phone number, message ID, and failure reason.
  - `WARNING`: Logged at the end of each batch run if 1 or more messages fail (`Batch complete: X sent, Y failed`).
  - `INFO`: Logged at the end of each batch run when all messages succeed (`Batch complete: X sent, 0 failed`).

#### Red Warning Banner on Review Page:
- **URL**: [http://127.0.0.1:8001/attendance/review/](http://127.0.0.1:8001/attendance/review/)
- **Visual Alert**: Whenever 1 or more WhatsApp messages fail today, a prominent red warning banner is displayed at the top of the page:
  `⚠️ X message(s) failed to send today — check WhatsApp session!`
- Includes a **"Retry Dispatch"** button to re-trigger the background Playwright sender on demand.
