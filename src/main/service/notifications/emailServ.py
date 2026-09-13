import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

from src.main.core.notificationConfig import SMTPConfig

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


def enviar_codigo_verificacion(destinatario: str, nombre: str, codigo: str) -> bool:
    """Envía el código de confirmación de 6 dígitos al correo del usuario."""
    logger.info("=== CODIGO DE VERIFICACION PARA %s (%s): %s ===", destinatario, nombre, codigo)
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP no configurado; se omite el envío real del correo (código en log: %s)", codigo)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_USER
        msg["To"] = destinatario
        msg["Subject"] = f"{codigo} es tu código de confirmación de Yaku"

        nombre_saludo = nombre.strip() if nombre else "Agricultor"
        texto_plano = (
            f"Hola {nombre_saludo},\n\n"
            f"Tu código de confirmación para verificar tu cuenta en Yaku es: {codigo}\n\n"
            f"Ingresa este código de 6 dígitos en la página de verificación para activar tu cuenta.\n"
            f"Este código expira en 30 minutos.\n\n"
            f"Saludos,\nEquipo Yaku"
        )

        texto_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; }}
    .card {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-top: 5px solid #0d9488; }}
    .logo {{ font-size: 24px; font-weight: bold; color: #0d9488; text-align: center; margin-bottom: 20px; }}
    .title {{ font-size: 20px; color: #1e293b; text-align: center; font-weight: 600; margin-bottom: 12px; }}
    .code-box {{ background: #f0fdf4; border: 2px dashed #22c55e; border-radius: 8px; padding: 18px; text-align: center; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #15803d; margin: 24px 0; }}
    .footer {{ font-size: 12px; color: #64748b; text-align: center; margin-top: 24px; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🌿 YAKU</div>
    <div class="title">Código de Confirmación</div>
    <p>Hola <strong>{nombre_saludo}</strong>,</p>
    <p>Gracias por unirte al Sistema de Riego Inteligente Yaku. Para verificar tu correo y acceder a tu cuenta, ingresa el siguiente código:</p>
    <div class="code-box">{codigo}</div>
    <p>Este código es válido por <strong>30 minutos</strong>. Si no solicitaste esta cuenta, puedes ignorar este mensaje.</p>
    <div class="footer">Sistema de Riego Inteligente Yaku &bull; Notificación Automática</div>
  </div>
</body>
</html>"""

        msg.attach(MIMEText(texto_plano, "plain", "utf-8"))
        msg.attach(MIMEText(texto_html, "html", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, destinatario, msg.as_string())

        logger.info("Correo con código de confirmación enviado exitosamente a %s", destinatario)
        return True
    except Exception:
        logger.exception("Falló el envío de correo con código de confirmación a %s", destinatario)
        return False


def enviar_codigo_recuperacion(destinatario: str, nombre: str, codigo: str) -> bool:
    """Envía el código de 6 dígitos para recuperación de contraseña al correo del usuario."""
    logger.info("=== CODIGO DE RECUPERACION PARA %s (%s): %s ===", destinatario, nombre, codigo)
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP no configurado; se omite el envío real del correo (código en log: %s)", codigo)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_USER
        msg["To"] = destinatario
        msg["Subject"] = f"{codigo} es tu código de recuperación de contraseña de Yaku"

        nombre_saludo = nombre.strip() if nombre else "Usuario"
        texto_plano = (
            f"Hola {nombre_saludo},\n\n"
            f"Hemos recibido una solicitud para restablecer la contraseña de tu cuenta en Yaku.\n"
            f"Tu código de recuperación es: {codigo}\n\n"
            f"Ingresa este código de 6 dígitos junto con tu nueva contraseña en la página de recuperación.\n"
            f"Este código expira en 15 minutos.\n\n"
            f"Si tú no solicitaste este cambio, por favor ignora este mensaje o contacta a soporte.\n\n"
            f"Saludos,\nEquipo Yaku"
        )

        texto_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; }}
    .card {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-top: 5px solid #0284c7; }}
    .logo {{ font-size: 24px; font-weight: bold; color: #0284c7; text-align: center; margin-bottom: 20px; }}
    .title {{ font-size: 20px; color: #1e293b; text-align: center; font-weight: 600; margin-bottom: 12px; }}
    .code-box {{ background: #f0f9ff; border: 2px dashed #0284c7; border-radius: 8px; padding: 18px; text-align: center; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #0369a1; margin: 24px 0; }}
    .footer {{ font-size: 12px; color: #64748b; text-align: center; margin-top: 24px; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🌿 YAKU</div>
    <div class="title">Recuperación de Contraseña</div>
    <p>Hola <strong>{nombre_saludo}</strong>,</p>
    <p>Hemos recibido una solicitud para restablecer la contraseña de acceso a tu cuenta. Ingresa el siguiente código de confirmación:</p>
    <div class="code-box">{codigo}</div>
    <p>Este código es válido por <strong>15 minutos</strong>. Si tú no solicitaste este cambio, puedes ignorar este mensaje de forma segura.</p>
    <div class="footer">Sistema de Riego Inteligente Yaku &bull; Seguridad de Cuenta</div>
  </div>
</body>
</html>"""

        msg.attach(MIMEText(texto_plano, "plain", "utf-8"))
        msg.attach(MIMEText(texto_html, "html", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, destinatario, msg.as_string())

        logger.info("Correo con código de recuperación enviado exitosamente a %s", destinatario)
        return True
    except Exception:
        logger.exception("Falló el envío de correo con código de recuperación a %s", destinatario)
        return False

