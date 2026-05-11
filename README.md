# Event Notification Sender

A modern, self-hosted bulk email tool with a clean web UI and persistent storage.
Upload an Excel file, configure your SMTP server (Gmail with App Password supported),
map Name/Email columns, write personalized messages, preview, and send bulk emails with full history tracking.

## Features

- **Persistent SMTP Config** - Save your SMTP settings securely in SQLite database
- **Email History Tracking** - Complete audit trail of all sent emails with success/failure status
- **Statistics Dashboard** - View total emails sent, success rate, and batch history
- **SMTP Support** - Gmail, Outlook, or custom SMTP with TLS/SSL. Test connection with one click
- **Excel Upload** - Supports `.xlsx` and `.xls`. Auto-detects Name and Email columns using regex
- **Custom Mail-Merge** - Use `{ColumnName}` placeholders in subject and HTML body
- **Live Preview** - See exactly what the first 5 recipients will receive
- **Detailed Results** - Success/failure per recipient with error messages
- **Modern UI** - Step-by-step wizard built with Tailwind CSS
- **Dockerized** - Run with a single command. SQLite database for persistence
- **Input Validation** - Comprehensive validation and error handling
- **Security** - Password masking, file size limits, and sanitized inputs

## Quick Start

### Option 1: Docker Hub (Recommended)

Pull and run the pre-built image:

```bash
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/data:/app/data \
  --name event-notifier \
  YOUR_DOCKERHUB_USERNAME/event-notifier:latest
```

Then open http://localhost:8000 in your browser.

### Option 2: Docker Compose

```bash
git clone https://github.com/sameeralam3127/event-notifier.git
cd event-notifier
docker-compose up -d
```

For local development with hot reloading:

```bash
docker compose -f docker-compose.dev.yml up --build
```

### Option 3: Build from Source

```bash
git clone https://github.com/sameeralam3127/event-notifier.git
cd event-notifier
docker build -t event-notifier .
docker run -d -p 8000:8000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/data:/app/data \
  event-notifier
```

## Usage Guide

### Step 1: Configure SMTP

1. Enter your SMTP server details:
   - **Host**: `smtp.gmail.com` (for Gmail)
   - **Port**: `587` (TLS) or `465` (SSL)
   - **Username**: Your email address
   - **Password**: Your email password or App Password
   - **From Email**: The sender email address

2. Click **Save SMTP** to persist configuration
3. Click **Test Connection** to verify settings

#### Gmail Setup

For Gmail, you need to create an App Password:

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Step Verification
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Generate a new app password for "Mail"
5. Use this 16-character password in the tool

### Step 2: Upload Excel File

1. Click **Choose File** and select your `.xlsx` or `.xls` file
2. The tool will automatically detect Name and Email columns
3. Preview the first 5 rows to verify data

**Excel Requirements:**

- First row must contain column headers
- Must have at least one column with email addresses
- Maximum 1000 recipients per batch
- Maximum file size: 10MB

### Step 3: Map Columns & Compose Message

1. Confirm or adjust the Name and Email column mappings
2. Write your email subject and body
3. Use placeholders like `{Name}`, `{Email}`, or any column name from your Excel
4. HTML is supported in the body

**Example:**

```
Subject: Hi {Name}, invitation to our event

Body:
Dear {Name},

You are invited to our upcoming event!

Event Details:
- Date: {EventDate}
- Location: {Venue}

Best regards,
The Team
```

### Step 4: Preview & Send

1. Click **Preview Emails** to see how the first 5 emails will look
2. Review the merged content
3. Click **Send to All** to send emails to all recipients
4. View detailed results with success/failure status

### View History

Click **View History** to see:

- All previously sent emails
- Batch statistics
- Success/failure rates
- Error messages for failed emails

## Data Persistence

All data is stored in SQLite database at `/app/data/event_notifier.db`:

- **SMTP Configuration**: Saved and auto-loaded on next visit
- **Email History**: Complete audit trail of all sent emails
- **Batch History**: Track multiple sending sessions
- **Statistics**: Overall performance metrics

The database is persisted using Docker volumes, so your data survives container restarts.

## Configuration

### Environment Variables

You can customize the application using environment variables:

```bash
docker run -d \
  -p 8000:8000 \
  -e APP_ENV=production \
  -e EVENT_NOTIFIER_MAX_UPLOAD_MB=10 \
  -e EVENT_NOTIFIER_MAX_RECIPIENTS=1000 \
  -e EVENT_NOTIFIER_SECURE_COOKIES=false \
  -e EVENT_NOTIFIER_DB_PATH=/app/data/event_notifier.db \
  -e EVENT_NOTIFIER_UPLOAD_DIR=/app/uploads \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/data:/app/data \
  event-notifier
```

### Volume Mounts

- `/app/uploads` - Temporary storage for uploaded Excel files
- `/app/data` - SQLite database for persistent storage

### Production Defaults

- Runs as a non-root container user
- Includes `/health` for container and load-balancer checks
- Hides FastAPI docs when `APP_ENV=production`
- Adds browser security headers and HTTP-only session cookies
- Supports `EVENT_NOTIFIER_SECURE_COOKIES=true` when served behind HTTPS
- Uses named Docker volumes in production compose and bind mounts in dev compose

## Security Features

- **Password Sanitization**: Removes non-ASCII characters that cause authentication errors
- **Input Validation**: Validates email addresses, file types, and sizes
- **File Size Limits**: Maximum 10MB per Excel file
- **Recipient Limits**: Maximum 1000 recipients per batch
- **Password Masking**: Passwords are masked when retrieving saved config
- **Session Management**: Secure session handling with HTTP-only cookies
- **Safe Rendering**: Uploaded spreadsheet values and history data are escaped in the UI

## API Endpoints

The application provides REST API endpoints:

- `POST /api/configure-smtp` - Save SMTP configuration
- `GET /api/get-smtp-config` - Retrieve saved SMTP config
- `POST /api/test-smtp` - Test SMTP connection
- `POST /api/upload-excel` - Upload Excel file
- `POST /api/set-mapping` - Set column mappings
- `POST /api/preview` - Preview merged emails
- `POST /api/send-emails` - Send bulk emails
- `GET /api/email-history` - Get email send history
- `GET /api/batch-history` - Get batch history
- `GET /api/statistics` - Get overall statistics
- `GET /health` - Health check endpoint

## Troubleshooting

### SMTP Authentication Errors

If you see "UnicodeEncodeError" or authentication failures:

- Make sure there are no extra spaces in username/password
- For Gmail, use an App Password, not your regular password
- Verify 2-Step Verification is enabled for Gmail

### Excel Upload Issues

- Ensure first row contains column headers
- Check that email column contains valid email addresses
- File must be `.xlsx` or `.xls` format
- File size must be under 10MB

### Connection Issues

- Verify SMTP host and port are correct
- Check firewall settings
- For Gmail, ensure "Less secure app access" is not required
- Test with the built-in connection test feature

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- UI styled with [Tailwind CSS](https://tailwindcss.com/)
- Excel parsing with [openpyxl](https://openpyxl.readthedocs.io/)

## Support

For issues, questions, or suggestions:

- Open an issue on [GitHub](https://github.com/sameeralam3127/event-notifier/issues)
- Contact: sameeralam3127@gmail.com

---

Made by Sameer Alam
