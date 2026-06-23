import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from src.config import SMTPConfig

load_dotenv()
logger = logging.getLogger(__name__)

SMTP_SERVER = SMTPConfig.SERVER
SMTP_PORT = SMTPConfig.PORT
SMTP_USER = SMTPConfig.USER
SMTP_PASSWORD = SMTPConfig.PASSWORD

def enviar_correo_alerta(destinatario: str, asunto: str, mensaje: str) -> bool:
    """Envía un correo electrónico de alerta de forma síncrona usando SMTP."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP no configurado; se omite el correo")
        return False
    
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = destinatario
        msg["Subject"] = asunto

        msg.attach(MIMEText(mensaje, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, destinatario, msg.as_string())
        
        logger.info("Correo enviado")
        return True
    except Exception:
        logger.exception("Falló el envío de correo")
        return False
