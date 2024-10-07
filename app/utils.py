from passlib.context import CryptContext
import re
import qrcode
import base64
from io import BytesIO

# إعداد التشفير باستخدام bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash(password: str) -> str:
    """
    Hashes a password using bcrypt.

    Args:
        password (str): The plain text password to hash.

    Returns:
        str: The hashed password.
    """
    return pwd_context.hash(password)


def verify(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain text password against a hashed password.

    Args:
        plain_password (str): The plain text password.
        hashed_password (str): The hashed password to compare against.

    Returns:
        bool: True if the passwords match, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def check_content_against_rules(content: str, rules: List[str]) -> bool:
    for rule in rules:
        if re.search(rule, content, re.IGNORECASE):
            return False
    return True


def generate_qr_code(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()
