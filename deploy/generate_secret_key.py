#!/usr/bin/env python3
"""
Generate a secure Django SECRET_KEY for production use.

Usage:
    python generate_secret_key.py

This script generates a cryptographically secure random key suitable
for use as DJANGO_SECRET_KEY in production environments.
"""

import secrets
import string


def generate_django_secret_key(length=50):
    """
    Generate a secure random secret key for Django.
    
    Args:
        length (int): Length of the key (default: 50 characters)
        
    Returns:
        str: A secure random string suitable for DJANGO_SECRET_KEY
    """
    # Use secrets module for cryptographically strong random values
    # This is more secure than random module
    
    # Method 1: URL-safe base64 encoded (recommended)
    key_urlsafe = secrets.token_urlsafe(length)
    
    # Method 2: Hex encoding
    key_hex = secrets.token_hex(length)
    
    # Method 3: Custom character set (Django-style)
    chars = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
    key_custom = ''.join(secrets.choice(chars) for _ in range(length))
    
    return key_urlsafe, key_hex, key_custom


def main():
    print("=" * 80)
    print("Django SECRET_KEY Generator")
    print("=" * 80)
    print()
    print("IMPORTANT: Never reuse the same key across different environments!")
    print("           Keep your secret key secret - never commit it to version control!")
    print()
    print("-" * 80)
    print()
    
    # Generate keys
    key_urlsafe, key_hex, key_custom = generate_django_secret_key(50)
    
    print("Option 1 (Recommended - URL-safe base64):")
    print(f"  {key_urlsafe}")
    print()
    
    print("Option 2 (Hexadecimal):")
    print(f"  {key_hex}")
    print()
    
    print("Option 3 (Django-style with special chars):")
    print(f"  {key_custom}")
    print()
    
    print("-" * 80)
    print()
    print("Usage in .env file:")
    print()
    print(f"  DJANGO_SECRET_KEY={key_urlsafe}")
    print()
    print("-" * 80)
    print()
    print("✅ Copy one of the keys above to your .env file")
    print("✅ Each key is cryptographically secure")
    print("✅ All three options are equally secure - choose any one")
    print()
    print("🔐 Security Tips:")
    print("   - Never use the same key in development and production")
    print("   - Never commit .env file to version control")
    print("   - Store backups of .env securely (password manager)")
    print("   - Rotate keys periodically (requires re-deployment)")
    print("   - If key is compromised, generate a new one immediately")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
