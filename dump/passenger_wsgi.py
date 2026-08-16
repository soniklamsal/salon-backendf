"""
Passenger WSGI Entry Point for cPanel Deployment

This file is the entry point for Phusion Passenger running on cPanel.
It sets up the Django application and handles the WSGI interface.

IMPORTANT: 
- This file should be in the root of your application directory
- Make sure the path below matches your actual application structure
- Python version should be 3.10 or higher
"""

import sys
import os
from pathlib import Path

# ==============================================================================
# Path Configuration
# ==============================================================================

# Get the directory containing this file (application root)
PASSENGER_ROOT = Path(__file__).resolve().parent

# Add the application directory to Python path
sys.path.insert(0, str(PASSENGER_ROOT))

# If your Django project is in a subdirectory, adjust this path
# Example: if manage.py is in a 'backend' subfolder, use:
# sys.path.insert(0, str(PASSENGER_ROOT / 'backend'))

# ==============================================================================
# Environment Setup
# ==============================================================================

# Load environment variables from .env file
# CRITICAL: Ensure .env file exists in PASSENGER_ROOT with production settings
from dotenv import load_dotenv
env_path = PASSENGER_ROOT / '.env'

if not env_path.exists():
    raise RuntimeError(
        f".env file not found at {env_path}. "
        "Copy .env.production.example to .env and configure it."
    )

load_dotenv(env_path)

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Verify DEBUG is False in production
if os.environ.get('DJANGO_DEBUG', '').lower() in ('true', '1', 'yes', 'on'):
    raise RuntimeError(
        "DJANGO_DEBUG is set to True. This is a security risk in production! "
        "Set DJANGO_DEBUG=False in your .env file."
    )

# ==============================================================================
# Django Application
# ==============================================================================

from django.core.wsgi import get_wsgi_application

# Create the WSGI application
application = get_wsgi_application()

# ==============================================================================
# Production Checklist Verification
# ==============================================================================

def verify_production_config():
    """
    Basic production configuration check.
    This runs on startup to catch critical misconfigurations.
    """
    errors = []
    
    # Check SECRET_KEY
    secret_key = os.environ.get('DJANGO_SECRET_KEY', '')
    if not secret_key or secret_key == 'dev-only-insecure-key-change-me':
        errors.append("DJANGO_SECRET_KEY is missing or still using dev default")
    
    # Check DEBUG
    if os.environ.get('DJANGO_DEBUG', '').lower() in ('true', '1', 'yes', 'on'):
        errors.append("DJANGO_DEBUG is True - must be False in production")
    
    # Check ALLOWED_HOSTS
    allowed_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
    if not allowed_hosts or allowed_hosts in ('localhost', '127.0.0.1'):
        errors.append("DJANGO_ALLOWED_HOSTS must include your production domain")
    
    # Check DATABASE_URL
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url or 'sqlite' in db_url:
        errors.append("DATABASE_URL must be set to MySQL in production")
    
    # Check Cloudinary
    if not all([
        os.environ.get('CLOUDINARY_CLOUD_NAME'),
        os.environ.get('CLOUDINARY_API_KEY'),
        os.environ.get('CLOUDINARY_API_SECRET')
    ]):
        errors.append("Cloudinary credentials are incomplete")
    
    if errors:
        error_msg = "Production Configuration Errors:\n" + "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(error_msg)

# Run verification on startup
try:
    verify_production_config()
except RuntimeError as e:
    # Log error but don't crash - let Django's own checks handle it
    import sys
    print(f"WARNING: {e}", file=sys.stderr)

# ==============================================================================
# Passenger Configuration Notes
# ==============================================================================
"""
cPanel Passenger Configuration:

1. In cPanel → Setup Python App:
   - Python version: 3.10 or higher
   - Application root: /home/username/salon-backend
   - Application URL: your domain or subdomain
   - Application startup file: passenger_wsgi.py
   - Application Entry point: application

2. After setup, install dependencies:
   source /home/username/virtualenv/salon-backend/3.10/bin/activate
   pip install -r requirements.txt

3. Run migrations:
   python manage.py migrate

4. Load data:
   python manage.py loaddata salon_data.json

5. Create superuser:
   python manage.py createsuperuser

6. Collect static files:
   python manage.py collectstatic --no-input

7. Restart app:
   touch tmp/restart.txt

Environment Variables:
- Set in .env file (NOT in cPanel Python App settings)
- .env must be in the same directory as this file
- Ensure .env has correct permissions (chmod 600)

Logs:
- Application logs: Check cPanel error logs
- Django logs: Configured to output to stdout/stderr
- To debug: Set DJANGO_LOG_LEVEL=DEBUG in .env temporarily

Troubleshooting:
- 500 Error: Check cPanel error logs for Python traceback
- Module not found: Verify virtual environment and pip install
- Static files 404: Run collectstatic and verify STATIC_ROOT
- Database errors: Check DATABASE_URL format and MySQL access
- Permission denied: Check file/folder permissions

Restarting:
- Method 1: cPanel → Setup Python App → Restart button
- Method 2: SSH: touch ~/tmp/restart.txt
- Method 3: Update this file and save (triggers auto-reload)
"""

# ==============================================================================
# Performance Tips
# ==============================================================================
"""
Production Performance Optimization:

1. Database:
   - Use DB_CONN_MAX_AGE=600 to pool connections
   - Add indexes to frequently queried fields
   - Monitor slow queries with DJANGO_SQL_LOG_LEVEL=WARNING

2. Caching (optional but recommended):
   - Install Redis or Memcached
   - Configure Django caching in settings
   - Cache homepage API response

3. Static Files:
   - Ensure WhiteNoise is serving static files efficiently
   - Consider CDN for static files if high traffic
   - Run collectstatic with --no-input

4. Media Files:
   - Cloudinary handles media storage and CDN
   - Verify Cloudinary auto-optimization is enabled
   - Use appropriate image formats (WebP where possible)

5. Monitoring:
   - Set up error email notifications in Django
   - Monitor Cloudinary usage and bandwidth
   - Check database size and query performance
   - Review cPanel resource usage regularly
"""