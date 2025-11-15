"""
Validierungs-Funktionen für E-Mails, PLZ, Telefonnummern
"""
import re
from email_validator import validate_email, EmailNotValidError
import phonenumbers
from typing import Optional


def validate_email_format(email: str) -> bool:
    """
    Validiert E-Mail-Format nach RFC-Standard

    Args:
        email: Zu validierende E-Mail-Adresse

    Returns:
        bool: True wenn gültig, False sonst
    """
    if not email:
        return False

    try:
        # Validiere und normalisiere
        validation = validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def validate_postal_code(postal_code: str, allowed_prefixes: list = None) -> bool:
    """
    Validiert deutsche PLZ (5-stellig) und optional nach Präfix

    Args:
        postal_code: PLZ als String
        allowed_prefixes: Liste erlaubter Anfangsziffern (z.B. ['5'] für NRW)

    Returns:
        bool: True wenn gültig
    """
    if not postal_code:
        return False

    # Entferne Leerzeichen
    postal_code = postal_code.strip()

    # Prüfe Format: 5 Ziffern
    if not re.match(r'^\d{5}$', postal_code):
        return False

    # Prüfe Präfix wenn angegeben
    if allowed_prefixes:
        first_digit = postal_code[0]
        return first_digit in allowed_prefixes

    return True


def validate_phone_number(phone: str, region: str = "DE") -> Optional[str]:
    """
    Validiert und formatiert Telefonnummer

    Args:
        phone: Telefonnummer
        region: Ländercode (default: DE)

    Returns:
        str: Formatierte Nummer oder None wenn ungültig
    """
    if not phone:
        return None

    try:
        parsed = phonenumbers.parse(phone, region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed,
                phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
    except phonenumbers.NumberParseException:
        pass

    return None


def extract_postal_code_from_location(location: str) -> Optional[str]:
    """
    Extrahiert PLZ aus Standort-String

    Args:
        location: z.B. "50667 Köln" oder "Köln, 50667"

    Returns:
        str: PLZ oder None
    """
    if not location:
        return None

    # Suche 5-stellige Zahl
    match = re.search(r'\b(\d{5})\b', location)
    if match:
        return match.group(1)

    return None


def normalize_company_name(name: str) -> str:
    """
    Normalisiert Firmennamen für Deduplizierung

    Args:
        name: Firmenname

    Returns:
        str: Normalisierter Name (lowercase, ohne Rechtsform)
    """
    if not name:
        return ""

    # Konvertiere zu lowercase
    normalized = name.lower().strip()

    # Entferne Rechtsformen
    rechtsformen = [
        r'\s+gmbh\s*&\s*co\.\s*kg\b',
        r'\s+gmbh\s*&\s*co\b',
        r'\s+ag\s*&\s*co\.\s*kg\b',
        r'\s+gmbh\b',
        r'\s+ag\b',
        r'\s+kg\b',
        r'\s+ug\b',
        r'\s+ohg\b',
        r'\s+gbr\b',
        r'\s+e\.v\.\b',
        r'\s+se\b',
    ]

    for form in rechtsformen:
        normalized = re.sub(form, '', normalized)

    # Entferne mehrfache Leerzeichen
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def is_business_email(email: str, company_domain: Optional[str] = None) -> bool:
    """
    Prüft ob E-Mail geschäftlich ist (nicht Freemail)

    Args:
        email: E-Mail-Adresse
        company_domain: Optional: Erwartete Firmendomain

    Returns:
        bool: True wenn geschäftliche E-Mail
    """
    if not validate_email_format(email):
        return False

    email_lower = email.lower()

    # Freemail-Provider ausschließen
    freemail_providers = [
        'gmail.com', 'googlemail.com',
        'yahoo.com', 'yahoo.de',
        'hotmail.com', 'hotmail.de',
        'outlook.com', 'outlook.de',
        'web.de', 'gmx.de', 'gmx.net',
        't-online.de', 'freenet.de',
        'aol.com', 'icloud.com'
    ]

    domain = email_lower.split('@')[1]

    if domain in freemail_providers:
        return False

    # Optional: Prüfe ob Domain zur Firma passt
    if company_domain:
        company_domain = company_domain.lower().replace('www.', '')
        return domain == company_domain or domain.endswith('.' + company_domain)

    return True


def extract_gender_from_name(first_name: str) -> str:
    """
    Versucht Anrede aus Vornamen zu ermitteln (DE)

    Args:
        first_name: Vorname

    Returns:
        str: "Herr", "Frau" oder "Herr/Frau" (fallback)
    """
    if not first_name:
        return "Herr/Frau"

    first_name = first_name.strip().lower()

    # Typisch weibliche Endungen (Deutsch)
    female_patterns = [
        r'.*a$',  # Anna, Julia, Maria
        r'.*e$',  # Christine, Helene, Renate
        r'.*ine$',  # Christine, Sabine
        r'.*ia$',  # Julia, Maria
        r'.*ke$',  # Friederike, Heike
    ]

    # Typisch männliche Namen (Beispiele)
    male_names = [
        'alexander', 'andreas', 'bernd', 'christian', 'daniel',
        'dennis', 'dirk', 'frank', 'jan', 'jens', 'jochen',
        'jörg', 'karl', 'klaus', 'lars', 'lukas', 'marco',
        'markus', 'martin', 'matthias', 'max', 'michael',
        'oliver', 'patrick', 'paul', 'peter', 'philipp',
        'ralf', 'robert', 'stefan', 'thomas', 'tim', 'tobias',
        'tom', 'uwe', 'volker', 'werner', 'wolfgang'
    ]

    # Typisch weibliche Namen
    female_names = [
        'anna', 'andrea', 'angela', 'angelika', 'anja', 'anke',
        'barbara', 'beate', 'birgit', 'brigitte', 'carmen',
        'christiane', 'christine', 'claudia', 'daniela', 'doris',
        'elena', 'elisabeth', 'eva', 'gabi', 'gabriele',
        'heike', 'helga', 'ines', 'ingrid', 'jana', 'jennifer',
        'jessica', 'julia', 'karin', 'katja', 'katrin',
        'kirsten', 'kristina', 'laura', 'lisa', 'manuela',
        'maria', 'marion', 'martina', 'melanie', 'monika',
        'nadine', 'nicole', 'nina', 'petra', 'sabine',
        'sandra', 'sarah', 'silke', 'simone', 'stefanie',
        'susanne', 'tanja', 'ursula', 'ute', 'vanessa'
    ]

    # Direkte Namensübereinstimmung
    if first_name in male_names:
        return "Herr"
    if first_name in female_names:
        return "Frau"

    # Pattern-Matching für weibliche Endungen
    for pattern in female_patterns:
        if re.match(pattern, first_name):
            return "Frau"

    # Default: Herr/Frau
    return "Herr/Frau"
