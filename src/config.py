# src/config.py
"""Centralized configuration for environment variables.

Loads .env once and provides two config classes:
- SMTPConfig   – SMTP settings for email notifications.
- VAPIDConfig  – VAPID keys and claim email for Web Push.
All other modules should import these instead of calling ``os.getenv`` directly.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env at import time
load_dotenv()

class SMTPConfig:
    SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    PORT: int = int(os.getenv("SMTP_PORT", "587"))
    USER: str = os.getenv("SMTP_USER", "")
    PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

class VAPIDConfig:
    PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "")
    PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
    CLAIMS_EMAIL: str = os.getenv("VAPID_CLAIMS_EMAIL", "soporte@yaku.com")
