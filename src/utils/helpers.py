"""
Helper-Funktionen für Rate Limiting, Retry-Logik, Logging
"""
import time
import random
import logging
from typing import Optional, Callable, Any
from functools import wraps
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from fake_useragent import UserAgent

# Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate Limiter für Request-Verzögerung"""

    def __init__(self, delay: float = 2.5, jitter: float = 0.5):
        """
        Args:
            delay: Basis-Verzögerung in Sekunden
            jitter: Zufällige Variation (+/- jitter Sekunden)
        """
        self.delay = delay
        self.jitter = jitter
        self.last_request = 0

    def wait(self):
        """Wartet die erforderliche Zeit"""
        now = time.time()
        elapsed = now - self.last_request

        # Berechne Wartezeit mit Jitter
        wait_time = self.delay + random.uniform(-self.jitter, self.jitter)

        if elapsed < wait_time:
            sleep_time = wait_time - elapsed
            logger.debug(f"Rate limiting: Warte {sleep_time:.2f}s")
            time.sleep(sleep_time)

        self.last_request = time.time()


def get_random_user_agent() -> str:
    """
    Generiert zufälligen User-Agent

    Returns:
        str: User-Agent String
    """
    try:
        ua = UserAgent()
        return ua.random
    except:
        # Fallback
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get_request_headers(referer: Optional[str] = None) -> dict:
    """
    Generiert Request-Headers

    Args:
        referer: Optional Referer-URL

    Returns:
        dict: Headers
    """
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    if referer:
        headers['Referer'] = referer

    return headers


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.RequestException, TimeoutError))
)
def fetch_with_retry(url: str, session: Optional[requests.Session] = None,
                     timeout: int = 30, **kwargs) -> requests.Response:
    """
    Führt HTTP-Request mit Retry-Logik aus

    Args:
        url: Ziel-URL
        session: Optional requests.Session
        timeout: Timeout in Sekunden
        **kwargs: Weitere requests-Parameter

    Returns:
        Response-Objekt

    Raises:
        requests.exceptions.RequestException bei Fehler nach max. Retries
    """
    if session is None:
        session = requests.Session()

    if 'headers' not in kwargs:
        kwargs['headers'] = get_request_headers()

    logger.debug(f"Fetching: {url}")

    response = session.get(url, timeout=timeout, **kwargs)
    response.raise_for_status()

    return response


def clean_text(text: Optional[str]) -> str:
    """
    Bereinigt Text von überflüssigen Whitespaces

    Args:
        text: Zu bereinigender Text

    Returns:
        str: Bereinigter Text
    """
    if not text:
        return ""

    import re

    # Entferne mehrfache Leerzeichen, Tabs, Newlines
    cleaned = re.sub(r'\s+', ' ', text)

    # Trimme
    cleaned = cleaned.strip()

    return cleaned


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extrahiert Domain aus URL

    Args:
        url: URL

    Returns:
        str: Domain oder None
    """
    if not url:
        return None

    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path

        # Entferne www.
        domain = domain.replace('www.', '')

        return domain.lower()
    except:
        return None


def deduplicate_by_key(items: list, key: str) -> list:
    """
    Dedupliziert Liste nach bestimmtem Key

    Args:
        items: Liste von Dictionaries
        key: Dictionary-Key für Deduplizierung

    Returns:
        list: Deduplizierte Liste
    """
    seen = set()
    unique_items = []

    for item in items:
        value = item.get(key)
        if value and value not in seen:
            seen.add(value)
            unique_items.append(item)

    return unique_items


def chunk_list(lst: list, chunk_size: int) -> list:
    """
    Teilt Liste in Chunks

    Args:
        lst: Zu teilende Liste
        chunk_size: Größe der Chunks

    Returns:
        list: Liste von Chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def safe_get(dictionary: dict, *keys, default=None) -> Any:
    """
    Sicherer Zugriff auf verschachtelte Dictionary-Keys

    Args:
        dictionary: Dictionary
        *keys: Verschachtelte Keys
        default: Default-Wert bei Fehler

    Returns:
        Wert oder default
    """
    result = dictionary

    for key in keys:
        try:
            result = result[key]
        except (KeyError, TypeError, IndexError):
            return default

    return result


def log_progress(current: int, total: int, prefix: str = "Progress"):
    """
    Logged Fortschritt

    Args:
        current: Aktueller Stand
        total: Gesamt
        prefix: Log-Präfix
    """
    percentage = (current / total * 100) if total > 0 else 0
    logger.info(f"{prefix}: {current}/{total} ({percentage:.1f}%)")


def measure_time(func: Callable) -> Callable:
    """
    Decorator zum Messen der Ausführungszeit

    Args:
        func: Zu messende Funktion

    Returns:
        Wrapped function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()

        duration = end_time - start_time
        logger.info(f"{func.__name__} dauerte {duration:.2f}s")

        return result

    return wrapper
