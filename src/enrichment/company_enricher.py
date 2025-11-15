"""
Firmen-Enrichment: Website-Recherche und Datenextraktion
"""
import logging
import re
from typing import Dict, Optional, List
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests

from ..utils.helpers import (
    fetch_with_retry, get_request_headers, clean_text,
    extract_domain_from_url, RateLimiter
)
from ..utils.validators import validate_email_format

logger = logging.getLogger(__name__)


class CompanyEnricher:
    """
    Enrichment für Firmendaten via Website-Recherche
    """

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: Optional RateLimiter
        """
        self.rate_limiter = rate_limiter or RateLimiter(delay=2.0)

    def enrich_company(self, company_name: str, initial_location: str = "") -> Dict:
        """
        Reichert Firmendaten an

        Args:
            company_name: Firmenname
            initial_location: Standort (optional)

        Returns:
            Dict: Angereicherte Firmendaten
        """
        logger.info(f"Enriching company: {company_name}")

        enriched_data = {
            'company_name': company_name,
            'location': initial_location,
            'website': '',
            'imprint_url': '',
            'career_url': '',
            'company_description': '',
            'industry': '',
            'employees_count': ''
        }

        # 1. Finde Website via Google-Suche
        website = self.find_company_website(company_name, initial_location)

        if website:
            enriched_data['website'] = website

            # 2. Extrahiere Daten von Website
            try:
                website_data = self.extract_website_data(website)
                enriched_data.update(website_data)
            except Exception as e:
                logger.error(f"Error extracting website data for {company_name}: {e}")

        return enriched_data

    def find_company_website(self, company_name: str, location: str = "") -> Optional[str]:
        """
        Findet offizielle Website via Google-Suche

        Args:
            company_name: Firmenname
            location: Standort

        Returns:
            str: Website-URL oder None
        """
        self.rate_limiter.wait()

        # Google-Suche: "Firmenname Standort"
        query = f"{company_name}"
        if location:
            query += f" {location}"

        search_url = f"https://www.google.de/search?q={requests.utils.quote(query)}&hl=de"

        try:
            headers = get_request_headers()
            response = requests.get(search_url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            # Erstes organisches Suchergebnis (nicht Werbung)
            search_results = soup.find_all('div', class_='g')

            for result in search_results[:3]:  # Top 3 Ergebnisse prüfen
                link_elem = result.find('a', href=True)

                if link_elem:
                    url = link_elem['href']

                    # Extrahiere tatsächliche URL (Google verwendet /url?q= Redirects)
                    if '/url?q=' in url:
                        url = url.split('/url?q=')[1].split('&')[0]

                    # Validiere URL
                    if self._is_valid_company_url(url, company_name):
                        logger.info(f"Found website for {company_name}: {url}")
                        return url

        except Exception as e:
            logger.error(f"Error finding website for {company_name}: {e}")

        return None

    def _is_valid_company_url(self, url: str, company_name: str) -> bool:
        """
        Validiert ob URL zur Firma gehört

        Args:
            url: URL
            company_name: Firmenname

        Returns:
            bool: True wenn valide
        """
        if not url:
            return False

        # Ausschluss von Job-Portalen, Social Media, etc.
        excluded_domains = [
            'indeed', 'stepstone', 'xing', 'linkedin', 'facebook',
            'twitter', 'instagram', 'youtube', 'kununu', 'glassdoor',
            'monster', 'jobware', 'stellenanzeigen', 'wikipedia'
        ]

        url_lower = url.lower()

        for domain in excluded_domains:
            if domain in url_lower:
                return False

        # URL sollte http/https sein
        if not url.startswith('http'):
            return False

        return True

    def extract_website_data(self, website_url: str) -> Dict:
        """
        Extrahiert Daten von Firmen-Website

        Args:
            website_url: Website-URL

        Returns:
            Dict: Extrahierte Daten
        """
        self.rate_limiter.wait()

        data = {
            'imprint_url': '',
            'career_url': '',
            'company_description': '',
            'contact_emails': []
        }

        try:
            response = fetch_with_retry(website_url)
            soup = BeautifulSoup(response.content, 'lxml')

            # 1. Finde Impressum
            data['imprint_url'] = self._find_imprint_url(soup, website_url)

            # 2. Finde Karriere-Seite
            data['career_url'] = self._find_career_url(soup, website_url)

            # 3. Extrahiere Beschreibung (Meta-Tags)
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                data['company_description'] = clean_text(meta_desc.get('content', ''))

            # 4. Finde E-Mails auf Hauptseite
            data['contact_emails'] = self._extract_emails_from_page(soup)

        except Exception as e:
            logger.error(f"Error extracting website data: {e}")

        return data

    def _find_imprint_url(self, soup: BeautifulSoup, base_url: str) -> str:
        """
        Findet Impressum-URL

        Args:
            soup: BeautifulSoup-Objekt
            base_url: Basis-URL

        Returns:
            str: Impressum-URL
        """
        # Deutsche Impressum-Keywords
        imprint_keywords = [
            'impressum', 'imprint', 'kontakt', 'contact',
            'über uns', 'about', 'legal'
        ]

        links = soup.find_all('a', href=True)

        for link in links:
            link_text = clean_text(link.get_text()).lower()
            href = link['href'].lower()

            for keyword in imprint_keywords:
                if keyword in link_text or keyword in href:
                    url = urljoin(base_url, link['href'])
                    return url

        return ""

    def _find_career_url(self, soup: BeautifulSoup, base_url: str) -> str:
        """
        Findet Karriere/Jobs-Seite

        Args:
            soup: BeautifulSoup-Objekt
            base_url: Basis-URL

        Returns:
            str: Karriere-URL
        """
        career_keywords = [
            'karriere', 'career', 'jobs', 'stellenangebote',
            'stellenanzeigen', 'join', 'arbeiten bei'
        ]

        links = soup.find_all('a', href=True)

        for link in links:
            link_text = clean_text(link.get_text()).lower()
            href = link['href'].lower()

            for keyword in career_keywords:
                if keyword in link_text or keyword in href:
                    url = urljoin(base_url, link['href'])
                    return url

        return ""

    def _extract_emails_from_page(self, soup: BeautifulSoup) -> List[str]:
        """
        Extrahiert E-Mail-Adressen von Seite

        Args:
            soup: BeautifulSoup-Objekt

        Returns:
            List[str]: E-Mail-Adressen
        """
        emails = set()

        # Regex für E-Mails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

        # Suche im gesamten Text
        page_text = soup.get_text()
        found_emails = re.findall(email_pattern, page_text)

        for email in found_emails:
            if validate_email_format(email):
                emails.add(email.lower())

        # Suche in mailto:-Links
        mailto_links = soup.find_all('a', href=re.compile(r'^mailto:'))
        for link in mailto_links:
            email = link['href'].replace('mailto:', '').split('?')[0]
            if validate_email_format(email):
                emails.add(email.lower())

        return list(emails)

    def get_jobs_from_career_page(self, career_url: str, max_jobs: int = 3) -> List[Dict]:
        """
        Extrahiert Jobs von Karriere-Seite

        Args:
            career_url: Karriere-Seiten-URL
            max_jobs: Max. Anzahl Jobs

        Returns:
            List[Dict]: Job-Listings
        """
        if not career_url:
            return []

        jobs = []

        try:
            self.rate_limiter.wait()

            response = fetch_with_retry(career_url)
            soup = BeautifulSoup(response.content, 'lxml')

            # Suche nach Job-Links
            # Typische Patterns: <a> mit Keywords wie "entwickler", "administrator", etc.
            job_keywords = [
                'entwickler', 'developer', 'engineer', 'administrator',
                'devops', 'scientist', 'architect', 'consultant',
                'manager', 'analyst', 'specialist'
            ]

            links = soup.find_all('a', href=True)

            for link in links:
                if len(jobs) >= max_jobs:
                    break

                link_text = clean_text(link.get_text())

                # Prüfe ob Link Job-relevante Keywords enthält
                if any(keyword in link_text.lower() for keyword in job_keywords):
                    job_url = urljoin(career_url, link['href'])

                    jobs.append({
                        'title': link_text,
                        'url': job_url
                    })

        except Exception as e:
            logger.error(f"Error extracting jobs from career page: {e}")

        return jobs
