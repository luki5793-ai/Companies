"""
Google Jobs Scraper (Google for Jobs)
"""
import logging
import re
from typing import List, Dict, Optional
from urllib.parse import quote_plus, urljoin
import requests
from bs4 import BeautifulSoup

from ..utils.helpers import fetch_with_retry, get_request_headers, clean_text, RateLimiter
from ..utils.validators import extract_postal_code_from_location, validate_postal_code

logger = logging.getLogger(__name__)


class GoogleJobsScraper:
    """
    Scraper für Google Jobs (Google for Jobs)
    Nutzt Google-Suche mit jobs-Operator
    """

    GOOGLE_SEARCH_URL = "https://www.google.de/search"

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: Optional RateLimiter-Instanz
        """
        self.rate_limiter = rate_limiter or RateLimiter(delay=3.5)

    def search_jobs(self, query: str, location: str, max_results: int = 50,
                    postal_code_filter: List[str] = None, days_back: int = 90) -> List[Dict]:
        """
        Sucht Jobs über Google Jobs

        Args:
            query: Suchbegriff
            location: Standort
            max_results: Max. Anzahl Ergebnisse
            postal_code_filter: Filter nach PLZ-Präfix
            days_back: Jobs der letzten X Tage

        Returns:
            List[Dict]: Liste von Job-Daten
        """
        logger.info(f"Searching Google Jobs: query='{query}', location='{location}'")

        jobs = []
        start = 0
        page = 0

        while len(jobs) < max_results and page < 5:  # Max 5 Seiten
            self.rate_limiter.wait()

            # Google-Suche mit "jobs" Operator
            search_query = f"{query} jobs {location}"

            params = {
                'q': search_query,
                'ibp': 'htl;jobs',  # Google Jobs aktivieren
                'start': start,
                'hl': 'de',
                'gl': 'de'
            }

            url = self._build_search_url(params)

            try:
                # Spezielle Headers für Google
                headers = get_request_headers()
                headers['Accept-Language'] = 'de-DE,de;q=0.9'

                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'lxml')

                # Google Jobs verwendet strukturierte Daten
                # Suche nach Job-Postings im Schema.org Format
                job_scripts = soup.find_all('script', type='application/ld+json')

                found_jobs = False

                for script in job_scripts:
                    try:
                        import json
                        data = json.loads(script.string)

                        # JobPosting Schema
                        if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                            job_data = self._parse_job_posting_schema(data)
                            if job_data:
                                # PLZ-Filter
                                if postal_code_filter:
                                    plz = extract_postal_code_from_location(job_data.get('location', ''))
                                    if plz and not validate_postal_code(plz, postal_code_filter):
                                        continue

                                jobs.append(job_data)
                                found_jobs = True
                                logger.debug(f"Found job: {job_data.get('company_name')} - {job_data.get('job_title')}")

                        # Liste von JobPostings
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                                    job_data = self._parse_job_posting_schema(item)
                                    if job_data:
                                        if postal_code_filter:
                                            plz = extract_postal_code_from_location(job_data.get('location', ''))
                                            if plz and not validate_postal_code(plz, postal_code_filter):
                                                continue

                                        jobs.append(job_data)
                                        found_jobs = True

                    except Exception as e:
                        logger.debug(f"Error parsing schema: {e}")
                        continue

                # Fallback: Parse HTML direkt
                if not found_jobs:
                    html_jobs = self._parse_google_jobs_html(soup)
                    for job in html_jobs:
                        if postal_code_filter:
                            plz = extract_postal_code_from_location(job.get('location', ''))
                            if plz and not validate_postal_code(plz, postal_code_filter):
                                continue

                        jobs.append(job)
                        found_jobs = True

                if not found_jobs:
                    logger.info("Keine weiteren Jobs gefunden")
                    break

                start += 10
                page += 1
                logger.info(f"Google Jobs page {page} completed: {len(jobs)} jobs collected")

            except Exception as e:
                logger.error(f"Error scraping Google Jobs page {page}: {e}")
                break

        logger.info(f"Google Jobs scraping completed: {len(jobs)} jobs found")
        return jobs[:max_results]

    def _build_search_url(self, params: Dict) -> str:
        """
        Baut Google Search URL

        Args:
            params: URL-Parameter

        Returns:
            str: URL
        """
        query_string = "&".join([f"{k}={quote_plus(str(v))}" for k, v in params.items()])
        return f"{self.GOOGLE_SEARCH_URL}?{query_string}"

    def _parse_job_posting_schema(self, schema_data: Dict) -> Optional[Dict]:
        """
        Parst JobPosting Schema.org Daten

        Args:
            schema_data: JSON-LD Schema

        Returns:
            Dict: Job-Daten
        """
        try:
            # Firmenname
            hiring_org = schema_data.get('hiringOrganization', {})
            company_name = hiring_org.get('name', '')

            if not company_name:
                return None

            # Job-Titel
            job_title = schema_data.get('title', '')

            # Standort
            job_location = schema_data.get('jobLocation', {})
            if isinstance(job_location, list):
                job_location = job_location[0] if job_location else {}

            address = job_location.get('address', {})
            if isinstance(address, dict):
                location = address.get('addressLocality', '')
                postal_code = address.get('postalCode', '')
                if postal_code:
                    location = f"{postal_code} {location}"
            else:
                location = str(address)

            # Beschreibung
            description = schema_data.get('description', '')

            # URL
            job_url = schema_data.get('url', '')

            return {
                'source': 'google_jobs',
                'company_name': clean_text(company_name),
                'job_title': clean_text(job_title),
                'job_url': job_url,
                'location': clean_text(location),
                'job_description': clean_text(description)[:500],  # Kürzen
                'postal_code': extract_postal_code_from_location(location)
            }

        except Exception as e:
            logger.error(f"Error parsing job schema: {e}")
            return None

    def _parse_google_jobs_html(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Fallback: Parse Google Jobs aus HTML

        Args:
            soup: BeautifulSoup-Objekt

        Returns:
            List[Dict]: Job-Daten
        """
        jobs = []

        try:
            # Suche nach Job-Listings (Google ändert häufig Struktur)
            job_divs = soup.find_all('div', class_=re.compile(r'PwjeAc|job'))

            for div in job_divs:
                try:
                    # Firmenname
                    company_elem = div.find('div', class_=re.compile(r'vNEEBe'))
                    company_name = clean_text(company_elem.get_text()) if company_elem else ""

                    # Job-Titel
                    title_elem = div.find('div', class_=re.compile(r'BjJfJf'))
                    job_title = clean_text(title_elem.get_text()) if title_elem else ""

                    # Standort
                    location_elem = div.find('div', class_=re.compile(r'Qk80Jf'))
                    location = clean_text(location_elem.get_text()) if location_elem else ""

                    if company_name and job_title:
                        jobs.append({
                            'source': 'google_jobs',
                            'company_name': company_name,
                            'job_title': job_title,
                            'job_url': '',
                            'location': location,
                            'job_description': '',
                            'postal_code': extract_postal_code_from_location(location)
                        })

                except Exception as e:
                    continue

        except Exception as e:
            logger.debug(f"Error parsing Google Jobs HTML: {e}")

        return jobs
