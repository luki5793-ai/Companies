"""
StepStone Job-Scraper für Deutschland
"""
import logging
import re
from typing import List, Dict, Optional
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup

from ..utils.helpers import fetch_with_retry, get_request_headers, clean_text, RateLimiter
from ..utils.validators import extract_postal_code_from_location, validate_postal_code

logger = logging.getLogger(__name__)


class StepStoneScraper:
    """
    Scraper für StepStone.de
    """

    BASE_URL = "https://www.stepstone.de"
    SEARCH_URL = "https://www.stepstone.de/jobs"

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: Optional RateLimiter-Instanz
        """
        self.rate_limiter = rate_limiter or RateLimiter(delay=3.0)

    def search_jobs(self, query: str, location: str, max_results: int = 50,
                    postal_code_filter: List[str] = None, days_back: int = 90) -> List[Dict]:
        """
        Sucht Jobs auf StepStone

        Args:
            query: Suchbegriff
            location: Standort
            max_results: Max. Anzahl Ergebnisse
            postal_code_filter: Filter nach PLZ-Präfix
            days_back: Jobs der letzten X Tage

        Returns:
            List[Dict]: Liste von Job-Daten
        """
        logger.info(f"Searching StepStone: query='{query}', location='{location}'")

        jobs = []
        page = 1

        while len(jobs) < max_results:
            self.rate_limiter.wait()

            # Baue Search-URL
            url = self._build_search_url(query, location, page)

            try:
                response = fetch_with_retry(url)
                soup = BeautifulSoup(response.content, 'lxml')

                # Extrahiere Job-Listings
                # StepStone verwendet häufig <article> Tags für Jobs
                job_cards = soup.find_all('article', attrs={'data-at': 'job-item'})

                # Fallback: Suche nach alternativen Selektoren
                if not job_cards:
                    job_cards = soup.find_all('article', class_=re.compile(r'listing'))

                if not job_cards:
                    logger.info("Keine weiteren Jobs gefunden")
                    break

                for card in job_cards:
                    if len(jobs) >= max_results:
                        break

                    job_data = self._parse_job_card(card)

                    if job_data:
                        # PLZ-Filter
                        if postal_code_filter:
                            plz = extract_postal_code_from_location(job_data.get('location', ''))
                            if plz and not validate_postal_code(plz, postal_code_filter):
                                continue

                        jobs.append(job_data)
                        logger.debug(f"Found job: {job_data.get('company_name')} - {job_data.get('job_title')}")

                page += 1
                logger.info(f"StepStone page {page-1} completed: {len(jobs)} jobs collected")

                # Check Pagination
                next_page = soup.find('a', {'data-at': 'pagination-next'})
                if not next_page:
                    logger.info("Keine weiteren Seiten verfügbar")
                    break

            except Exception as e:
                logger.error(f"Error scraping StepStone page {page}: {e}")
                break

        logger.info(f"StepStone scraping completed: {len(jobs)} jobs found")
        return jobs

    def _build_search_url(self, query: str, location: str, page: int = 1) -> str:
        """
        Baut StepStone Search-URL

        Args:
            query: Suchbegriff
            location: Standort
            page: Seitennummer

        Returns:
            str: URL
        """
        # StepStone URL-Struktur: /jobs/[query]/in-[location]
        query_slug = quote_plus(query.lower().replace(' ', '-'))
        location_slug = quote_plus(location.lower())

        url = f"{self.SEARCH_URL}/{query_slug}/in-{location_slug}"

        if page > 1:
            url += f"?page={page}"

        return url

    def _parse_job_card(self, card) -> Optional[Dict]:
        """
        Parst StepStone Job-Card

        Args:
            card: BeautifulSoup-Element

        Returns:
            Dict: Job-Daten
        """
        try:
            # Job-Titel und Link
            title_elem = card.find('a', attrs={'data-at': 'job-item-title'})
            if not title_elem:
                title_elem = card.find('h2').find('a') if card.find('h2') else None

            if title_elem:
                job_title = clean_text(title_elem.get_text())
                job_url = urljoin(self.BASE_URL, title_elem.get('href', ''))
            else:
                return None

            # Firmenname
            company_elem = card.find('a', attrs={'data-at': 'job-item-company-name'})
            if not company_elem:
                company_elem = card.find('span', class_=re.compile(r'company'))

            company_name = clean_text(company_elem.get_text()) if company_elem else ""

            if not company_name:
                return None

            # Standort
            location_elem = card.find('span', attrs={'data-at': 'job-item-location'})
            if not location_elem:
                location_elem = card.find('li', class_=re.compile(r'location'))

            location = clean_text(location_elem.get_text()) if location_elem else ""

            # Job-Beschreibung
            desc_elem = card.find('p', attrs={'data-at': 'job-item-snippet'})
            description = clean_text(desc_elem.get_text()) if desc_elem else ""

            return {
                'source': 'stepstone',
                'company_name': company_name,
                'job_title': job_title,
                'job_url': job_url,
                'location': location,
                'job_description': description,
                'postal_code': extract_postal_code_from_location(location)
            }

        except Exception as e:
            logger.error(f"Error parsing StepStone job card: {e}")
            return None

    def get_company_profile(self, company_name: str) -> Optional[Dict]:
        """
        Sucht Firmenprofil auf StepStone

        Args:
            company_name: Firmenname

        Returns:
            Dict: Firmen-Daten
        """
        try:
            self.rate_limiter.wait()

            # StepStone Firmenprofil-Suche
            search_url = f"{self.BASE_URL}/companies/{quote_plus(company_name.lower())}"

            response = fetch_with_retry(search_url)
            soup = BeautifulSoup(response.content, 'lxml')

            # Extrahiere Website
            website_elem = soup.find('a', class_=re.compile(r'company-website'))
            website = website_elem.get('href', '') if website_elem else ""

            return {
                'website': website
            }

        except Exception as e:
            logger.debug(f"Could not fetch company profile: {e}")
            return None
