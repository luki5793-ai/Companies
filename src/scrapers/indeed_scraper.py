"""
Indeed Job-Scraper für Deutschland
"""
import logging
import re
from typing import List, Dict, Optional
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
import time

from ..utils.helpers import fetch_with_retry, get_request_headers, clean_text, RateLimiter
from ..utils.validators import extract_postal_code_from_location, validate_postal_code

logger = logging.getLogger(__name__)


class IndeedScraper:
    """
    Scraper für Indeed.de
    """

    BASE_URL = "https://de.indeed.com"
    SEARCH_URL = "https://de.indeed.com/jobs"

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: Optional RateLimiter-Instanz
        """
        self.rate_limiter = rate_limiter or RateLimiter(delay=2.5)

    def search_jobs(self, query: str, location: str, max_results: int = 50,
                    postal_code_filter: List[str] = None, days_back: int = 90) -> List[Dict]:
        """
        Sucht Jobs auf Indeed

        Args:
            query: Suchbegriff (z.B. "Software Entwickler")
            location: Standort (z.B. "Köln")
            max_results: Max. Anzahl Ergebnisse
            postal_code_filter: Filter nach PLZ-Präfix
            days_back: Jobs der letzten X Tage

        Returns:
            List[Dict]: Liste von Job-Daten
        """
        logger.info(f"Searching Indeed: query='{query}', location='{location}'")

        jobs = []
        start = 0
        page = 0

        while len(jobs) < max_results:
            self.rate_limiter.wait()

            # Baue Search-URL
            params = {
                'q': query,
                'l': location,
                'fromage': days_back,  # Tage zurück
                'start': start,
                'filter': 0  # Keine gesponserten Jobs
            }

            url = self._build_search_url(params)

            try:
                response = fetch_with_retry(url)
                soup = BeautifulSoup(response.content, 'lxml')

                # Extrahiere Job-Cards
                job_cards = soup.find_all('div', class_=re.compile(r'job_seen_beacon'))

                if not job_cards:
                    logger.info("Keine weiteren Jobs gefunden")
                    break

                for card in job_cards:
                    if len(jobs) >= max_results:
                        break

                    job_data = self._parse_job_card(card)

                    if job_data:
                        # PLZ-Filter anwenden
                        if postal_code_filter:
                            plz = extract_postal_code_from_location(job_data.get('location', ''))
                            if plz and not validate_postal_code(plz, postal_code_filter):
                                logger.debug(f"Skipped (PLZ filter): {job_data.get('company_name')}")
                                continue

                        jobs.append(job_data)
                        logger.debug(f"Found job: {job_data.get('company_name')} - {job_data.get('job_title')}")

                # Nächste Seite
                start += 10
                page += 1
                logger.info(f"Indeed page {page} completed: {len(jobs)} jobs collected")

                # Check ob weitere Seiten vorhanden
                next_button = soup.find('a', {'aria-label': re.compile(r'Weiter|Next')})
                if not next_button:
                    logger.info("Keine weiteren Seiten verfügbar")
                    break

            except Exception as e:
                logger.error(f"Error scraping Indeed page {page}: {e}")
                break

        logger.info(f"Indeed scraping completed: {len(jobs)} jobs found")
        return jobs

    def _build_search_url(self, params: Dict) -> str:
        """
        Baut Search-URL

        Args:
            params: URL-Parameter

        Returns:
            str: Vollständige URL
        """
        query_string = "&".join([f"{k}={quote_plus(str(v))}" for k, v in params.items()])
        return f"{self.SEARCH_URL}?{query_string}"

    def _parse_job_card(self, card) -> Optional[Dict]:
        """
        Parst Job-Card Element

        Args:
            card: BeautifulSoup-Element

        Returns:
            Dict: Job-Daten oder None
        """
        try:
            # Firmenname
            company_elem = card.find('span', class_=re.compile(r'companyName'))
            company_name = clean_text(company_elem.get_text()) if company_elem else ""

            if not company_name:
                return None

            # Job-Titel
            title_elem = card.find('h2', class_=re.compile(r'jobTitle'))
            if title_elem:
                title_link = title_elem.find('a')
                job_title = clean_text(title_link.get_text()) if title_link else ""
                job_url = urljoin(self.BASE_URL, title_link.get('href', '')) if title_link else ""
            else:
                job_title = ""
                job_url = ""

            # Standort
            location_elem = card.find('div', class_=re.compile(r'companyLocation'))
            location = clean_text(location_elem.get_text()) if location_elem else ""

            # Job-Beschreibung (Snippet)
            desc_elem = card.find('div', class_=re.compile(r'job-snippet'))
            description = clean_text(desc_elem.get_text()) if desc_elem else ""

            # Job-ID (aus data-jk Attribut)
            job_id = card.get('data-jk', '')

            return {
                'source': 'indeed',
                'company_name': company_name,
                'job_title': job_title,
                'job_url': job_url,
                'location': location,
                'job_description': description,
                'job_id': job_id,
                'postal_code': extract_postal_code_from_location(location)
            }

        except Exception as e:
            logger.error(f"Error parsing job card: {e}")
            return None

    def get_job_details(self, job_url: str) -> Optional[Dict]:
        """
        Lädt vollständige Job-Details

        Args:
            job_url: Job-URL

        Returns:
            Dict: Erweiterte Job-Daten
        """
        if not job_url:
            return None

        try:
            self.rate_limiter.wait()

            response = fetch_with_retry(job_url)
            soup = BeautifulSoup(response.content, 'lxml')

            # Firmen-Website
            company_link = soup.find('a', {'data-tn-element': 'companyLink'})
            website = company_link.get('href', '') if company_link else ""

            # Vollständige Beschreibung
            desc_elem = soup.find('div', id='jobDescriptionText')
            full_description = clean_text(desc_elem.get_text()) if desc_elem else ""

            return {
                'website': website,
                'full_description': full_description
            }

        except Exception as e:
            logger.error(f"Error fetching job details: {e}")
            return None
