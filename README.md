# event-notifier# 📨 Event Notification Sender

A modern, self‑hosted mail‑merge tool with a clean web UI.  
Upload an Excel file, configure your SMTP server (Gmail with App Password supported),  
map Name/Email columns, write a personalised message, preview, and send bulk emails.

## ✨ Features

- **SMTP config** – Gmail, Outlook, or custom SMTP with TLS/SSL. Test connection with one click.
- **Excel upload** – supports `.xlsx` and `.xls`. Auto‑detects Name and Email columns using regex.
- **Custom mail‑merge** – use `{ColumnName}` placeholders in subject and HTML body.
- **Live preview** – see exactly what the first 5 recipients will receive.
- **Detailed results** – success/failure per recipient with error messages.
- **Modern UI** – step‑by‑step wizard built with Tailwind CSS.
- **Dockerised** – run with a single command. No external database needed.

## Quick Start with Docker

```bash
git clone https://github.com/sameeralam3127/event-notifier.git
cd event-notifier
docker-compose up --build
```
