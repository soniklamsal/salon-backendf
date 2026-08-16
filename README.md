# Salon Booking System - Django Backend

A production-ready Django REST API backend for a salon booking and appointment management system. Features secure payment screenshot handling, Clerk authentication integration, Cloudinary media storage, and a comprehensive admin interface.

## 🏗 Architecture

- **Framework**: Django 5.2 + Django REST Framework  
- **Authentication**: Clerk (JWT-based, optional)  
- **Database**: SQLite (dev) → MySQL/PostgreSQL (production)  
- **Media Storage**: Cloudinary (optional) + Private storage  
- **Admin**: Django Admin with Jazzmin theme  
- **Frontend**: Next.js (separate repository)

## 📋 Features

- **Public API**: Landing page content management
- **Booking System**: Appointment scheduling with payment proof
- **Authentication**: Optional Clerk JWT verification
- **Private Storage**: Secure payment screenshot handling
- **Admin Dashboard**: Content management + booking workflow
- **Rate Limiting**: IP-based throttling on write endpoints
- **Multi-database**: SQLite (dev), PostgreSQL, or MySQL (prod)

---

## 🚀 Quick Start (Development)

### Prerequisites

- Python 3.12+
- pip
- Virtual environment tool

### 1. Clone & Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env`:
```bash
# Generate a secret key
DJANGO_SECRET_KEY=your-secret-key-here

# Development settings
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000

# Optional: Clerk authentication
CLERK_ISSUER=https://your-app.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...

# Optional: Cloudinary storage
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

**Generate Secret Key**:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run Development Server

```bash
python manage.py runserver
```

Access:
- **API**: http://localhost:8000/api/v1/
- **Admin**: http://localhost:8000/admin/

---

## 🗄 Database Configuration

### SQLite (Development - Default)

No configuration needed. Database file: `db.sqlite3`

### PostgreSQL (Production - Recommended)

```bash
# .env
DATABASE_URL=postgres://user:password@localhost:5432/salon_db
```

### MySQL (Production - cPanel)

```bash
# .env
DATABASE_URL=mysql://user:password@localhost:3306/salon_db
```

**MySQL Requirements**:
- MySQL 5.7+ or MariaDB 10.2+
- utf8mb4 character set support
- InnoDB storage engine

**Install MySQL Driver**:
```bash
# May require MySQL development headers
# Ubuntu/Debian: sudo apt-get install default-libmysqlclient-dev
# CentOS/RHEL: sudo yum install mysql-devel
pip install mysqlclient
```

---

## 🔐 Authentication (Clerk)

### Optional Configuration

The booking system works without Clerk (anonymous bookings). To enable user accounts:

1. Create a Clerk application at https://clerk.com
2. Get credentials from Dashboard → API Keys
3. Set environment variables:

```bash
CLERK_ISSUER=https://your-app.clerk.accounts.dev
CLERK_SECRET_KEY=sk_live_...  # or sk_test_... for development
```

### How It Works

- **Without Clerk**: Bookings are anonymous (name/email/phone only)
- **With Clerk**: Bookings are linked to user accounts
  - User can view their booking history
  - Email auto-filled from account
  - Admin can see who booked what

---

## ☁ Media Storage

### Local Storage (Development - Default)

Files stored in:
- `media/` - Public uploads (hero images, service photos)
- `private-media/` - Payment screenshots (not web-accessible)

### Cloudinary (Production - Recommended)

Automatic when all three variables are set:

```bash
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key  
CLOUDINARY_API_SECRET=your-api-secret
```

**Optional**: Time-limited screenshot URLs (requires Cloudinary add-on):
```bash
CLOUDINARY_AUTH_TOKEN_KEY=your-auth-token-key
```

### File Upload Limits

```bash
MAX_UPLOAD_MB=8  # Maximum file size (default: 8MB)
MAX_UPLOAD_PIXELS=50000000  # Decompression bomb protection
```

---

## 📝 Management Commands

### Create Superuser

```bash
python manage.py createsuperuser
```

### Sync Clerk Users

Mirror Clerk accounts to Django admin (run after enabling Clerk):

```bash
python manage.py sync_clerk_users
```

### Backup Database & Media

```bash
python manage.py backup
# Creates timestamped files in backups/
```

### Collect Static Files

```bash
python manage.py collectstatic --no-input
```

### Seed Demo Content

```bash
python manage.py seed_content
```

---

## 🧪 Testing

### Run All Tests

```bash
python manage.py test
```

### Run Specific App Tests

```bash
python manage.py test api
python manage.py test bookings
python manage.py test core
```

### Test with Coverage

```bash
pip install coverage
coverage run --source='.' manage.py test
coverage report
coverage html  # Open htmlcov/index.html
```

**Current Test Status**: 192 tests, all passing ✓

---

## 🌐 Production Deployment

### Pre-Deployment Checklist

- [ ] Generate new production SECRET_KEY
- [ ] Set DJANGO_DEBUG=False
- [ ] Configure DATABASE_URL (MySQL/PostgreSQL)
- [ ] Set DJANGO_ALLOWED_HOSTS (your domain)
- [ ] Set CORS_ALLOWED_ORIGINS (Next.js frontend URL)
- [ ] Configure Clerk production credentials
- [ ] Configure Cloudinary production credentials
- [ ] Review SECURE_* settings in settings.py

### Environment Variables (Production)

```bash
# Security
DJANGO_SECRET_KEY=<long-random-string>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.yourdomain.com

# Database (MySQL example)
DATABASE_URL=mysql://user:password@localhost:3306/salon_db
DB_CONN_MAX_AGE=600

# CORS (your Next.js frontend)
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# SSL/HTTPS
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
TRUST_PROXY_SSL_HEADER=True

# Clerk (production)
CLERK_ISSUER=https://your-app.clerk.accounts.dev
CLERK_SECRET_KEY=sk_live_...

# Cloudinary (production)
CLOUDINARY_CLOUD_NAME=your-cloud
CLOUDINARY_API_KEY=your-key
CLOUDINARY_API_SECRET=your-secret
CLOUDINARY_AUTH_TOKEN_KEY=your-auth-key  # Optional

# Storage
PRIVATE_MEDIA_ROOT=/path/to/private-media
MAX_UPLOAD_MB=8

# Logging
DJANGO_LOG_LEVEL=INFO
```

### Deployment Steps

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Run Migrations

```bash
python manage.py migrate --no-input
```

#### 3. Create Superuser

```bash
python manage.py createsuperuser
```

#### 4. Collect Static Files

```bash
python manage.py collectstatic --no-input
```

#### 5. Configure WSGI Server

**Example with Gunicorn**:
```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

**Example with uWSGI**:
```bash
pip install uwsgi
uwsgi --http :8000 --module config.wsgi --master --processes 4
```

#### 6. Configure Web Server

**Nginx Example** (`/etc/nginx/sites-available/salon-api`):
```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /path/to/backend/staticfiles/;
    }

    location /media/ {
        alias /path/to/backend/media/;
    }
}
```

**Apache Example** (`.htaccess` or virtual host):
```apache
<VirtualHost *:80>
    ServerName api.yourdomain.com
    
    WSGIDaemonProcess salon python-path=/path/to/backend python-home=/path/to/.venv
    WSGIProcessGroup salon
    WSGIScriptAlias / /path/to/backend/config/wsgi.py

    <Directory /path/to/backend/config>
        <Files wsgi.py>
            Require all granted
        </Files>
    </Directory>

    Alias /static /path/to/backend/staticfiles
    Alias /media /path/to/backend/media

    <Directory /path/to/backend/staticfiles>
        Require all granted
    </Directory>

    <Directory /path/to/backend/media>
        Require all granted
    </Directory>
</VirtualHost>
```

### cPanel Deployment

1. **Create Python App** (cPanel → Setup Python App)
   - Python version: 3.12
   - Application root: `/home/user/backend`
   - Application startup file: `config/wsgi.py`

2. **Install Requirements**
   ```bash
   cd /home/user/backend
   source /home/user/virtualenv/backend/3.12/bin/activate
   pip install -r requirements.txt
   ```

3. **Create MySQL Database** (cPanel → MySQL Databases)
   - Create database: `user_salon`
   - Create user with all privileges
   - Note connection details

4. **Set Environment Variables** (cPanel → Python App → Environment)
   ```
   DJANGO_SECRET_KEY=...
   DJANGO_DEBUG=False
   DATABASE_URL=mysql://user:pass@localhost/user_salon
   DJANGO_ALLOWED_HOSTS=yourdomain.com
   CORS_ALLOWED_ORIGINS=https://yourdomain.com
   ```

5. **Run Migrations**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py collectstatic --no-input
   ```

6. **Restart Application** (cPanel → Python App → Restart)

---

## 🔍 Production Verification

### Health Check

```bash
curl https://api.yourdomain.com/api/v1/health/
# Expected: {"status": "ok"}
```

### Django Check

```bash
python manage.py check --deploy
# Should show no errors, only optional warnings
```

### Test API Endpoints

```bash
# Homepage payload
curl https://api.yourdomain.com/api/v1/homepage/

# Booking config
curl https://api.yourdomain.com/api/v1/booking-config/

# Services list
curl https://api.yourdomain.com/api/v1/services/
```

### Test Admin

Visit https://api.yourdomain.com/admin/ and log in with superuser account.

---

## 📚 API Documentation

Full API documentation is available in [`API.md`](./API.md).

### Key Endpoints

- `GET /api/v1/` - API root
- `GET /api/v1/health/` - Health check
- `GET /api/v1/homepage/` - Full landing page content
- `GET /api/v1/booking-config/` - Booking form configuration
- `GET /api/v1/services/` - Services list
- `GET /api/v1/barbers/` - Barbers list
- `GET /api/v1/my-bookings/` - User's bookings (authenticated)
- `POST /api/v1/appointments/` - Create booking (rate-limited: 10/hour)
- `POST /api/v1/contact-messages/` - Contact form (rate-limited: 20/hour)

### Rate Limits

- **Bookings**: 10 requests per hour per IP
- **Contact**: 20 requests per hour per IP
- **Read endpoints**: Unlimited

---

## 🛠 Troubleshooting

### "No module named 'mysqlclient'"

```bash
# Install MySQL development headers first
sudo apt-get install default-libmysqlclient-dev  # Ubuntu/Debian
sudo yum install mysql-devel  # CentOS/RHEL

# Then install Python package
pip install mysqlclient
```

### "Database is locked" (SQLite)

SQLite is not suitable for production with concurrent writes. Use MySQL or PostgreSQL.

### "DisallowedHost at /"

Add your domain to DJANGO_ALLOWED_HOSTS:
```bash
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,api.yourdomain.com
```

### Clerk Token Verification Fails

1. Check CLERK_ISSUER matches your Clerk application
2. Verify CLERK_SECRET_KEY is correct
3. Check Clerk dashboard for API key status
4. Test with: `python manage.py shell`
   ```python
   from common.clerk import is_configured
   print(is_configured())  # Should be True
   ```

### Static Files Not Loading

```bash
python manage.py collectstatic --no-input
# Verify STATIC_ROOT and STATIC_URL in settings
```

### Images Not Uploading

1. Check file size: MAX_UPLOAD_MB setting
2. Check image dimensions: MAX_UPLOAD_PIXELS setting
3. Verify Cloudinary credentials if using cloud storage
4. Check media/ and private-media/ directory permissions

---

## 🔒 Security Notes

### Secret Management

- **Never commit `.env`** to version control
- Rotate secrets before production deployment
- Use different secrets for dev/staging/production
- Store production secrets securely (password manager, secrets manager)

### Payment Screenshots

- Stored in `private-media/` (not web-accessible)
- Access controlled by Django view with authorization
- Cloudinary uploads use `type=authenticated` (signed URLs only)
- Three access methods:
  1. Booking owner (verified Clerk token)
  2. Admin staff user
  3. Time-limited signed token (for images in customer portal)

### HTTPS in Production

All security features automatically enable when `DEBUG=False`:
- HTTPS redirect
- Secure cookies
- HSTS headers
- Content sniffing protection

Disable only for initial deployment troubleshooting:
```bash
SECURE_SSL_REDIRECT=False
SECURE_HSTS_SECONDS=0
```

### Database Access

- Use least-privilege database user
- Never use root/admin database account
- Grant only: SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, DROP

---

## 📄 File Structure

```
backend/
├── api/                    # REST API endpoints
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── tests/
├── bookings/               # Appointments & bookings
│   ├── models.py           # Appointment, Barber, Service
│   ├── admin.py
│   ├── management/commands/
│   └── tests/
├── common/                 # Shared utilities
│   ├── clerk.py            # Clerk JWT verification
│   ├── storage.py          # Private file storage
│   ├── validators.py       # File upload validation
│   ├── exceptions.py       # API error handler
│   └── utils.py
├── config/                 # Django configuration
│   ├── settings.py         # Main settings
│   ├── urls.py             # URL routing
│   ├── wsgi.py             # WSGI entry point
│   └── jazzmin.py          # Admin UI config
├── core/                   # Site settings
│   ├── models.py           # SiteSettings, NavLink
│   ├── admin.py
│   └── management/commands/
├── sections/               # Landing page sections
│   ├── models.py           # Hero, Services, Gallery, etc.
│   └── admin.py
├── static/                 # Custom admin assets
│   └── admin/
├── media/                  # Public uploads (gitignored)
├── private-media/          # Private uploads (gitignored)
├── staticfiles/            # Collected static (gitignored)
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md               # This file
├── API.md                  # API documentation
└── PRODUCTION_AUDIT_REPORT.md
```

---

## 🤝 Contributing

This is a private salon booking system. For questions or support, contact the development team.

---

## 📜 License

Proprietary - All rights reserved

---

## 🆘 Support

For production issues:
1. Check logs: `journalctl -u gunicorn` or check web server error logs
2. Run Django checks: `python manage.py check --deploy`
3. Review this README's troubleshooting section
4. Check `PRODUCTION_AUDIT_REPORT.md` for security audit details

## 📦 Technology Stack

- **Backend**: Django 5.2, Django REST Framework 3.18
- **Database**: MySQL/PostgreSQL/SQLite
- **Authentication**: Clerk JWT
- **Storage**: Cloudinary + Local private storage
- **Admin**: Django Admin + Jazzmin theme
- **WSGI**: Gunicorn/uWSGI
- **Testing**: Django TestCase (192 tests)

---

**Built with Django** 🎸
