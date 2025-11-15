"""
Kontakt-Recherche: IT-Leiter, HR-Manager
"""
import logging
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from ..utils.helpers import fetch_with_retry, clean_text, RateLimiter
from ..utils.validators import (
    validate_email_format, is_business_email,
    validate_phone_number, extract_gender_from_name
)

logger = logging.getLogger(__name__)


class ContactFinder:
    """
    Findet Ansprechpartner (IT-Leiter, HR-Manager)
    """

    # Priorität 1: IT-Leitung
    IT_POSITION_KEYWORDS = [
        'cto', 'chief technology officer',
        'it-leiter', 'it leiter', 'leiter it',
        'head of it', 'head of technology',
        'it-manager', 'it manager',
        'technical director', 'technology director',
        'vp engineering', 'vice president engineering',
        'director of engineering',
        'entwicklungsleiter', 'leiter entwicklung'
    ]

    # Priorität 2: HR/Personal
    HR_POSITION_KEYWORDS = [
        'hr-manager', 'hr manager', 'human resources manager',
        'personalleiter', 'leiter personal',
        'head of hr', 'head of people',
        'hr-leitung', 'personalleitung',
        'recruiting manager', 'talent acquisition',
        'people manager', 'chro',
        'chief human resources officer'
    ]

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: Optional RateLimiter
        """
        self.rate_limiter = rate_limiter or RateLimiter(delay=2.5)

    def find_contacts(self, company_name: str, website: str,
                      imprint_url: str = "", max_contacts: int = 2) -> List[Dict]:
        """
        Findet Ansprechpartner für Firma

        Args:
            company_name: Firmenname
            website: Firmen-Website
            imprint_url: Impressum-URL
            max_contacts: Max. Anzahl Kontakte

        Returns:
            List[Dict]: Kontakte (sortiert nach Priorität)
        """
        logger.info(f"Finding contacts for: {company_name}")

        contacts = []

        # 1. Suche auf Team/Über uns Seiten
        team_contacts = self._search_team_pages(website, company_name)
        contacts.extend(team_contacts)

        # 2. Suche im Impressum
        if imprint_url and len(contacts) < max_contacts:
            imprint_contacts = self._search_imprint(imprint_url)
            contacts.extend(imprint_contacts)

        # 3. LinkedIn-Suche (optional, falls verfügbar)
        # Hier könnte LinkedIn-API Integration erfolgen
        # linkedin_contacts = self._search_linkedin(company_name)
        # contacts.extend(linkedin_contacts)

        # Dedupliziere und sortiere nach Priorität
        contacts = self._deduplicate_contacts(contacts)
        contacts = self._prioritize_contacts(contacts)

        # Limitiere auf max_contacts
        return contacts[:max_contacts]

    def _search_team_pages(self, website: str, company_name: str) -> List[Dict]:
        """
        Sucht Kontakte auf Team/Über uns Seiten

        Args:
            website: Website-URL
            company_name: Firmenname

        Returns:
            List[Dict]: Gefundene Kontakte
        """
        contacts = []

        # Mögliche Team-Seiten URLs
        team_urls = [
            f"{website}/team",
            f"{website}/ueber-uns",
            f"{website}/about",
            f"{website}/about-us",
            f"{website}/unternehmen",
            f"{website}/company",
            f"{website}/management",
            f"{website}/fuehrung"
        ]

        for url in team_urls:
            try:
                self.rate_limiter.wait()

                response = fetch_with_retry(url, timeout=15)
                soup = BeautifulSoup(response.content, 'lxml')

                # Extrahiere Personen-Informationen
                page_contacts = self._extract_contacts_from_page(soup, website)
                contacts.extend(page_contacts)

                if contacts:
                    logger.info(f"Found {len(page_contacts)} contacts on {url}")
                    break  # Stoppe nach erster erfolgreicher Seite

            except Exception as e:
                logger.debug(f"Could not access {url}: {e}")
                continue

        return contacts

    def _extract_contacts_from_page(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """
        Extrahiert Kontakte von HTML-Seite

        Args:
            soup: BeautifulSoup-Objekt
            base_url: Basis-URL

        Returns:
            List[Dict]: Kontakte
        """
        contacts = []

        # Suche nach typischen Team-Member Strukturen
        # Pattern 1: <div class="team-member">
        team_members = soup.find_all(['div', 'article', 'section'],
                                     class_=re.compile(r'team|member|person|mitarbeiter', re.I))

        for member in team_members:
            contact = self._parse_team_member(member)
            if contact:
                contacts.append(contact)

        # Pattern 2: Suche nach Namen + Position Kombinationen
        if not contacts:
            contacts = self._extract_contacts_from_text(soup)

        return contacts

    def _parse_team_member(self, element) -> Optional[Dict]:
        """
        Parst Team-Member HTML-Element

        Args:
            element: BeautifulSoup-Element

        Returns:
            Dict: Kontakt-Daten oder None
        """
        contact = {
            'first_name': '',
            'last_name': '',
            'position': '',
            'email': '',
            'phone': '',
            'salutation': 'Herr/Frau'
        }

        # Name
        name_elem = element.find(['h2', 'h3', 'h4', 'strong', 'b'],
                                 class_=re.compile(r'name|titel', re.I))
        if not name_elem:
            name_elem = element.find(['h2', 'h3', 'h4'])

        if name_elem:
            full_name = clean_text(name_elem.get_text())
            contact['first_name'], contact['last_name'] = self._split_name(full_name)

        # Position
        position_elem = element.find(['p', 'span', 'div'],
                                     class_=re.compile(r'position|role|titel|job', re.I))
        if position_elem:
            contact['position'] = clean_text(position_elem.get_text())

        # E-Mail
        email_elem = element.find('a', href=re.compile(r'^mailto:'))
        if email_elem:
            email = email_elem['href'].replace('mailto:', '').split('?')[0]
            if validate_email_format(email):
                contact['email'] = email.lower()

        # Telefon
        phone_elem = element.find('a', href=re.compile(r'^tel:'))
        if phone_elem:
            phone = phone_elem['href'].replace('tel:', '').strip()
            contact['phone'] = validate_phone_number(phone) or phone

        # Anrede ermitteln
        if contact['first_name']:
            contact['salutation'] = extract_gender_from_name(contact['first_name'])

        # Validiere: Mindestens Name und Position
        if contact['first_name'] and contact['last_name']:
            return contact

        return None

    def _extract_contacts_from_text(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extrahiert Kontakte aus Fließtext (Fallback)

        Args:
            soup: BeautifulSoup-Objekt

        Returns:
            List[Dict]: Kontakte
        """
        contacts = []

        # Suche nach Pattern: "Name, Position" oder "Position: Name"
        text = soup.get_text()

        # Pattern für deutsche Namen (Vorname Nachname)
        name_pattern = r'([A-ZÄÖÜ][a-zäöüß]+(?:\s+(?:von|van|de|der))?\s+[A-ZÄÖÜ][a-zäöüß]+)'

        # Finde alle Namen
        names = re.findall(name_pattern, text)

        for name in names[:10]:  # Max 10 versuchen
            # Suche Position in der Nähe
            position = self._find_position_near_name(text, name)

            if position:
                first_name, last_name = self._split_name(name)

                contact = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'position': position,
                    'email': '',
                    'phone': '',
                    'salutation': extract_gender_from_name(first_name)
                }

                contacts.append(contact)

        return contacts

    def _find_position_near_name(self, text: str, name: str) -> str:
        """
        Sucht Position in der Nähe eines Namens

        Args:
            text: Gesamttext
            name: Personenname

        Returns:
            str: Position oder ""
        """
        # Finde Position des Namens
        name_index = text.find(name)
        if name_index == -1:
            return ""

        # Extrahiere Kontext (100 Zeichen vor/nach)
        context = text[max(0, name_index - 100):name_index + len(name) + 100]

        # Suche nach IT/HR Positions-Keywords
        all_keywords = self.IT_POSITION_KEYWORDS + self.HR_POSITION_KEYWORDS

        for keyword in all_keywords:
            if keyword in context.lower():
                return keyword.title()

        return ""

    def _search_imprint(self, imprint_url: str) -> List[Dict]:
        """
        Sucht Kontakte im Impressum

        Args:
            imprint_url: Impressum-URL

        Returns:
            List[Dict]: Kontakte
        """
        contacts = []

        try:
            self.rate_limiter.wait()

            response = fetch_with_retry(imprint_url, timeout=15)
            soup = BeautifulSoup(response.content, 'lxml')

            # Geschäftsführer im Impressum
            text = soup.get_text()

            # Pattern: "Geschäftsführer: Name" oder "Vertretungsberechtigte: Name"
            gf_pattern = r'(?:Geschäftsführer|Geschäftsführung|Vertretungsberechtigte?|Managing Director)[:\s]+([A-ZÄÖÜ][a-zäöüß]+\s+[A-ZÄÖÜ][a-zäöüß]+)'

            matches = re.findall(gf_pattern, text)

            for match in matches[:2]:
                first_name, last_name = self._split_name(match)

                contact = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'position': 'Geschäftsführer',
                    'email': '',
                    'phone': '',
                    'salutation': extract_gender_from_name(first_name)
                }

                # Suche E-Mail im Impressum
                emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
                if emails and validate_email_format(emails[0]):
                    contact['email'] = emails[0].lower()

                contacts.append(contact)

        except Exception as e:
            logger.debug(f"Error searching imprint: {e}")

        return contacts

    def _split_name(self, full_name: str) -> tuple:
        """
        Teilt Vollständigen Namen in Vor- und Nachname

        Args:
            full_name: Vollständiger Name

        Returns:
            tuple: (Vorname, Nachname)
        """
        parts = full_name.strip().split()

        if len(parts) == 0:
            return "", ""
        elif len(parts) == 1:
            return parts[0], ""
        elif len(parts) == 2:
            return parts[0], parts[1]
        else:
            # Mehr als 2 Teile: Letzter Teil = Nachname, Rest = Vorname
            first_name = " ".join(parts[:-1])
            last_name = parts[-1]
            return first_name, last_name

    def _deduplicate_contacts(self, contacts: List[Dict]) -> List[Dict]:
        """
        Entfernt Duplikate

        Args:
            contacts: Kontakte

        Returns:
            List[Dict]: Deduplizierte Kontakte
        """
        seen = set()
        unique = []

        for contact in contacts:
            # Eindeutiger Key: Vorname + Nachname
            key = f"{contact['first_name']}_{contact['last_name']}".lower()

            if key not in seen and contact['first_name'] and contact['last_name']:
                seen.add(key)
                unique.append(contact)

        return unique

    def _prioritize_contacts(self, contacts: List[Dict]) -> List[Dict]:
        """
        Sortiert Kontakte nach Priorität (IT > HR > Rest)

        Args:
            contacts: Kontakte

        Returns:
            List[Dict]: Sortierte Kontakte
        """
        def get_priority(contact: Dict) -> int:
            position = contact.get('position', '').lower()

            # Priorität 1: IT-Positionen
            for keyword in self.IT_POSITION_KEYWORDS:
                if keyword in position:
                    return 1

            # Priorität 2: HR-Positionen
            for keyword in self.HR_POSITION_KEYWORDS:
                if keyword in position:
                    return 2

            # Priorität 3: Geschäftsführung
            if 'geschäftsführer' in position or 'ceo' in position:
                return 3

            # Priorität 4: Rest
            return 4

        # Sortiere nach Priorität (niedrigere Zahl = höhere Priorität)
        sorted_contacts = sorted(contacts, key=get_priority)

        return sorted_contacts
