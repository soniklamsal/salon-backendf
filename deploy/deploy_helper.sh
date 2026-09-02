#!/bin/bash
################################################################################
# Django Salon Backend - cPanel Deployment Helper Script
################################################################################
#
# This script helps automate common deployment tasks on cPanel.
# Run this after uploading files and creating the Python app in cPanel.
#
# Usage:
#   chmod +x deploy_helper.sh
#   ./deploy_helper.sh [command]
#
# Commands:
#   setup       - Initial setup (install dependencies, migrations, etc.)
#   migrate     - Run database migrations
#   collectstatic - Collect static files
#   loaddata    - Load data from salon_data.json
#   createadmin - Create superuser
#   backup      - Create database backup
#   restart     - Restart the application
#   check       - Run deployment checks
#   test        - Run test suite
#   all         - Run full deployment (setup + migrate + loaddata + collectstatic)
#
################################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration - UPDATE THESE
APP_DIR="$HOME/salon-backend"
VENV_DIR="$HOME/virtualenv/salon-backend/3.10"  # Update Python version as needed

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

activate_venv() {
    print_info "Activating virtual environment..."
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        print_success "Virtual environment activated"
    else
        print_error "Virtual environment not found at: $VENV_DIR"
        print_info "Please update VENV_DIR in this script"
        exit 1
    fi
}

check_env_file() {
    if [ ! -f "$APP_DIR/.env" ]; then
        print_error ".env file not found!"
        print_info "Copy .env.example to .env and configure it"
        exit 1
    fi
    print_success ".env file exists"
}

################################################################################
# Commands
################################################################################

cmd_setup() {
    print_header "Initial Setup"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    print_info "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    
    if [ $? -eq 0 ]; then
        print_success "Dependencies installed successfully"
    else
        print_error "Failed to install dependencies"
        exit 1
    fi
    
    print_success "Setup complete!"
}

cmd_migrate() {
    print_header "Running Migrations"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    print_info "Running database migrations..."
    python manage.py migrate
    
    if [ $? -eq 0 ]; then
        print_success "Migrations completed successfully"
    else
        print_error "Migrations failed"
        exit 1
    fi
}

cmd_collectstatic() {
    print_header "Collecting Static Files"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    print_info "Collecting static files..."
    python manage.py collectstatic --no-input --clear
    
    if [ $? -eq 0 ]; then
        print_success "Static files collected successfully"
    else
        print_error "Failed to collect static files"
        exit 1
    fi
}

cmd_loaddata() {
    print_header "Loading Data"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    if [ ! -f "dump/salon_data.json" ]; then
        print_error "salon_data.json not found in dump/ directory"
        exit 1
    fi
    
    print_info "Loading data from salon_data.json..."
    python manage.py loaddata dump/salon_data.json
    
    if [ $? -eq 0 ]; then
        print_success "Data loaded successfully (45 objects)"
    else
        print_error "Failed to load data"
        exit 1
    fi
}

cmd_createadmin() {
    print_header "Create Superuser"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    print_info "Creating superuser account..."
    print_warning "You will be prompted for username, email, and password"
    echo ""
    
    python manage.py createsuperuser
    
    if [ $? -eq 0 ]; then
        print_success "Superuser created successfully"
    else
        print_error "Failed to create superuser"
        exit 1
    fi
}

cmd_backup() {
    print_header "Creating Backup"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).json"
    
    print_info "Creating database backup: $BACKUP_FILE"
    python manage.py dumpdata \
        --natural-foreign \
        --natural-primary \
        --exclude contenttypes \
        --exclude auth.permission \
        --exclude sessions \
        --indent 2 \
        -o "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        print_success "Backup created: $BACKUP_FILE"
        ls -lh "$BACKUP_FILE"
    else
        print_error "Backup failed"
        exit 1
    fi
}

cmd_restart() {
    print_header "Restarting Application"
    
    print_info "Creating restart trigger..."
    mkdir -p "$HOME/tmp"
    touch "$HOME/tmp/restart.txt"
    
    if [ $? -eq 0 ]; then
        print_success "Application restart triggered"
        print_info "Wait 5-10 seconds for application to restart"
    else
        print_error "Failed to trigger restart"
        exit 1
    fi
}

cmd_check() {
    print_header "Running Deployment Checks"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    print_info "Running Django system check..."
    python manage.py check
    
    echo ""
    print_info "Running deployment-specific checks..."
    python manage.py check --deploy
    
    if [ $? -eq 0 ]; then
        print_success "All checks passed!"
    else
        print_warning "Some checks failed - review warnings above"
    fi
}

cmd_test() {
    print_header "Running Tests"
    
    cd "$APP_DIR" || exit 1
    activate_venv
    check_env_file
    
    print_info "Running test suite..."
    python manage.py test
    
    if [ $? -eq 0 ]; then
        print_success "All tests passed!"
    else
        print_error "Some tests failed"
        exit 1
    fi
}

cmd_all() {
    print_header "Full Deployment Process"
    
    print_info "This will run: setup → migrate → loaddata → collectstatic"
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Deployment cancelled"
        exit 0
    fi
    
    cmd_setup
    cmd_migrate
    cmd_loaddata
    cmd_collectstatic
    
    print_header "Deployment Complete!"
    print_success "Next steps:"
    echo "  1. Create superuser: ./deploy_helper.sh createadmin"
    echo "  2. Restart application: ./deploy_helper.sh restart"
    echo "  3. Run checks: ./deploy_helper.sh check"
    echo "  4. Test the API: curl https://yourdomain.com/api/v1/health/"
}

cmd_status() {
    print_header "Deployment Status Check"
    
    cd "$APP_DIR" || exit 1
    
    # Check .env
    if [ -f ".env" ]; then
        print_success ".env file exists"
    else
        print_error ".env file missing"
    fi
    
    # Check virtual environment
    if [ -f "$VENV_DIR/bin/python" ]; then
        print_success "Virtual environment exists"
        PYTHON_VERSION=$("$VENV_DIR/bin/python" --version)
        print_info "Python version: $PYTHON_VERSION"
    else
        print_error "Virtual environment not found"
    fi
    
    # Check if Django is installed
    if [ -f "$VENV_DIR/bin/python" ]; then
        activate_venv
        DJANGO_VERSION=$(python -c "import django; print(django.get_version())" 2>/dev/null)
        if [ -n "$DJANGO_VERSION" ]; then
            print_success "Django installed: $DJANGO_VERSION"
        else
            print_error "Django not installed"
        fi
    fi
    
    # Check database
    if [ -f ".env" ]; then
        activate_venv
        DB_CHECK=$(python manage.py check --database default 2>&1)
        if [ $? -eq 0 ]; then
            print_success "Database connection OK"
        else
            print_error "Database connection failed"
        fi
    fi
    
    # Check static files
    if [ -d "staticfiles" ] && [ "$(ls -A staticfiles)" ]; then
        STATIC_COUNT=$(find staticfiles -type f | wc -l)
        print_success "Static files collected ($STATIC_COUNT files)"
    else
        print_warning "Static files not collected yet"
    fi
    
    # Check data
    if [ -f ".env" ]; then
        activate_venv
        SERVICE_COUNT=$(python manage.py shell -c "from sections.models import Service; print(Service.objects.count())" 2>/dev/null)
        if [ -n "$SERVICE_COUNT" ] && [ "$SERVICE_COUNT" -gt 0 ]; then
            print_success "Database has data ($SERVICE_COUNT services)"
        else
            print_warning "Database appears empty"
        fi
    fi
}

cmd_help() {
    echo ""
    echo "Django Salon Backend - Deployment Helper"
    echo ""
    echo "Usage: ./deploy_helper.sh [command]"
    echo ""
    echo "Commands:"
    echo "  setup         - Install dependencies"
    echo "  migrate       - Run database migrations"
    echo "  collectstatic - Collect static files"
    echo "  loaddata      - Load initial data"
    echo "  createadmin   - Create superuser"
    echo "  backup        - Create database backup"
    echo "  restart       - Restart application"
    echo "  check         - Run deployment checks"
    echo "  test          - Run test suite"
    echo "  status        - Check deployment status"
    echo "  all           - Run full deployment"
    echo "  help          - Show this help"
    echo ""
    echo "Examples:"
    echo "  ./deploy_helper.sh all              # Full deployment"
    echo "  ./deploy_helper.sh setup            # Just install dependencies"
    echo "  ./deploy_helper.sh migrate          # Run migrations"
    echo "  ./deploy_helper.sh restart          # Restart app"
    echo ""
}

################################################################################
# Main
################################################################################

main() {
    # Check if running on the server
    if [ ! -d "$APP_DIR" ]; then
        print_error "Application directory not found: $APP_DIR"
        print_info "Please update APP_DIR in this script"
        exit 1
    fi
    
    # Parse command
    COMMAND=${1:-help}
    
    case $COMMAND in
        setup)
            cmd_setup
            ;;
        migrate)
            cmd_migrate
            ;;
        collectstatic|static)
            cmd_collectstatic
            ;;
        loaddata|load)
            cmd_loaddata
            ;;
        createadmin|admin)
            cmd_createadmin
            ;;
        backup)
            cmd_backup
            ;;
        restart)
            cmd_restart
            ;;
        check)
            cmd_check
            ;;
        test)
            cmd_test
            ;;
        all|deploy)
            cmd_all
            ;;
        status)
            cmd_status
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            print_error "Unknown command: $COMMAND"
            cmd_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
