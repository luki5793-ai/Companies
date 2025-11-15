"""
Main Apify Actor für B2B Lead-Generierung im IT-Recruiting-Bereich
"""
import asyncio
import logging
from typing import List, Dict
from apify import Actor

from .scrapers import IndeedScraper, StepStoneScraper, GoogleJobsScraper
from .filters.recruitment_filter import RecruitmentAgencyFilter
from .enrichment import CompanyEnricher, ContactFinder
from .utils.helpers import RateLimiter, deduplicate_by_key, log_progress
from .utils.validators import normalize_company_name
from .utils.exporters import LeadExporter

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class B2BLeadGenerator:
    """
    Haupt-Klasse für B2B Lead-Generierung
    """

    def __init__(self, config: Dict):
        """
        Args:
            config: Input-Konfiguration
        """
        self.config = config

        # Rate Limiter
        rate_limit = config.get('rateLimitDelay', 2.5)
        self.rate_limiter = RateLimiter(delay=rate_limit)

        # Scrapers initialisieren
        self.scrapers = {
            'indeed': IndeedScraper(self.rate_limiter),
            'stepstone': StepStoneScraper(self.rate_limiter),
            'google': GoogleJobsScraper(self.rate_limiter)
        }

        # Enrichment
        self.company_enricher = CompanyEnricher(self.rate_limiter)
        self.contact_finder = ContactFinder(self.rate_limiter)

        # Filter
        self.recruitment_filter = RecruitmentAgencyFilter()

    async def run(self) -> List[Dict]:
        """
        Hauptprozess

        Returns:
            List[Dict]: Generierte Leads
        """
        logger.info("=== B2B Lead Generator gestartet ===")

        # Phase 1: Job-Scraping
        logger.info("\n[PHASE 1] Job-Scraping")
        raw_jobs = await self._scrape_jobs()
        logger.info(f"Jobs gescraped: {len(raw_jobs)}")

        # Phase 2: Deduplizierung und Filterung
        logger.info("\n[PHASE 2] Deduplizierung und Filterung")
        unique_companies = self._deduplicate_companies(raw_jobs)
        logger.info(f"Unique Companies: {len(unique_companies)}")

        if self.config.get('excludeRecruitmentAgencies', True):
            unique_companies = self.recruitment_filter.filter_companies(unique_companies)
            logger.info(f"Nach Recruitment-Filter: {len(unique_companies)}")

        # Limitiere auf maxResults
        max_results = self.config.get('maxResults', 50)
        unique_companies = unique_companies[:max_results]

        # Phase 3: Firmen-Enrichment
        logger.info("\n[PHASE 3] Firmen-Enrichment")
        enriched_companies = await self._enrich_companies(unique_companies)

        # Phase 4: Kontakt-Recherche
        logger.info("\n[PHASE 4] Kontakt-Recherche")
        if self.config.get('enableContactEnrichment', True):
            leads = await self._find_contacts(enriched_companies)
        else:
            leads = enriched_companies

        # Phase 5: Job-Listing
        logger.info("\n[PHASE 5] Job-Listing Sammlung")
        leads = await self._collect_job_listings(leads)

        # Validierung
        valid_leads = [lead for lead in leads if LeadExporter.validate_lead(lead)]
        logger.info(f"Valide Leads: {len(valid_leads)}")

        logger.info("\n=== Lead-Generierung abgeschlossen ===")

        # Statistiken
        stats = LeadExporter.get_summary_statistics(valid_leads)
        logger.info(f"\nStatistiken:")
        logger.info(f"  - Gesamt Firmen: {stats.get('total_companies', 0)}")
        logger.info(f"  - Firmen mit 2 Kontakten: {stats.get('companies_with_2_contacts', 0)}")
        logger.info(f"  - Firmen mit 1 Kontakt: {stats.get('companies_with_1_contact', 0)}")
        logger.info(f"  - Gesamt Kontakte: {stats.get('total_contacts', 0)}")
        logger.info(f"  - Gesamt Jobs: {stats.get('total_jobs', 0)}")
        logger.info(f"  - Ø Jobs pro Firma: {stats.get('avg_jobs_per_company', 0)}")

        return valid_leads

    async def _scrape_jobs(self) -> List[Dict]:
        """
        Scraped Jobs von konfigurierten Portalen

        Returns:
            List[Dict]: Job-Daten
        """
        all_jobs = []

        search_queries = self.config.get('searchQueries', ['Software Entwickler'])
        locations = self.config.get('locations', ['Köln'])
        job_portals = self.config.get('jobPortals', ['indeed', 'stepstone'])
        postal_code_filter = self.config.get('postalCodeFilter', ['5'])
        max_results = self.config.get('maxResults', 50)
        days_back = self.config.get('jobDateRange', 90)

        # Berechne Jobs pro Portal/Query Kombination
        total_combinations = len(search_queries) * len(locations) * len(job_portals)
        jobs_per_combination = max(5, max_results // total_combinations)

        for portal_name in job_portals:
            if portal_name not in self.scrapers:
                logger.warning(f"Unbekanntes Portal: {portal_name}")
                continue

            scraper = self.scrapers[portal_name]

            for query in search_queries:
                for location in locations:
                    try:
                        logger.info(f"Scraping {portal_name}: {query} in {location}")

                        jobs = scraper.search_jobs(
                            query=query,
                            location=location,
                            max_results=jobs_per_combination,
                            postal_code_filter=postal_code_filter,
                            days_back=days_back
                        )

                        all_jobs.extend(jobs)
                        logger.info(f"  → {len(jobs)} Jobs gefunden")

                    except Exception as e:
                        logger.error(f"Error scraping {portal_name}: {e}")

        return all_jobs

    def _deduplicate_companies(self, jobs: List[Dict]) -> List[Dict]:
        """
        Dedupliziert Firmen

        Args:
            jobs: Job-Liste

        Returns:
            List[Dict]: Unique Firmen
        """
        # Gruppiere Jobs nach Firma
        company_map = {}

        for job in jobs:
            company_name = job.get('company_name', '').strip()
            if not company_name:
                continue

            normalized_name = normalize_company_name(company_name)

            if normalized_name not in company_map:
                company_map[normalized_name] = {
                    'company_name': company_name,
                    'location': job.get('location', ''),
                    'jobs': []
                }

            # Füge Job hinzu
            company_map[normalized_name]['jobs'].append({
                'title': job.get('job_title', ''),
                'url': job.get('job_url', ''),
                'source': job.get('source', ''),
                'description': job.get('job_description', '')
            })

        # Konvertiere zu Liste
        unique_companies = list(company_map.values())

        return unique_companies

    async def _enrich_companies(self, companies: List[Dict]) -> List[Dict]:
        """
        Reichert Firmendaten an

        Args:
            companies: Firmen-Liste

        Returns:
            List[Dict]: Angereicherte Firmen
        """
        enriched = []

        total = len(companies)

        for idx, company in enumerate(companies, 1):
            log_progress(idx, total, "Enrichment")

            try:
                enriched_data = self.company_enricher.enrich_company(
                    company_name=company['company_name'],
                    initial_location=company.get('location', '')
                )

                # Merge mit bestehenden Daten
                company.update(enriched_data)
                enriched.append(company)

            except Exception as e:
                logger.error(f"Error enriching {company['company_name']}: {e}")
                enriched.append(company)  # Füge trotzdem hinzu

        return enriched

    async def _find_contacts(self, companies: List[Dict]) -> List[Dict]:
        """
        Findet Ansprechpartner

        Args:
            companies: Firmen-Liste

        Returns:
            List[Dict]: Firmen mit Kontakten
        """
        max_contacts = self.config.get('maxContactsPerCompany', 2)

        total = len(companies)

        for idx, company in enumerate(companies, 1):
            log_progress(idx, total, "Kontakt-Recherche")

            website = company.get('website', '')
            if not website:
                logger.warning(f"Keine Website für {company['company_name']}")
                company['contacts'] = []
                continue

            try:
                contacts = self.contact_finder.find_contacts(
                    company_name=company['company_name'],
                    website=website,
                    imprint_url=company.get('imprint_url', ''),
                    max_contacts=max_contacts
                )

                company['contacts'] = contacts
                logger.info(f"  → {len(contacts)} Kontakte gefunden")

            except Exception as e:
                logger.error(f"Error finding contacts for {company['company_name']}: {e}")
                company['contacts'] = []

        return companies

    async def _collect_job_listings(self, companies: List[Dict]) -> List[Dict]:
        """
        Sammelt Job-Listings (aus bereits gescrapten Jobs + Karriere-Seite)

        Args:
            companies: Firmen-Liste

        Returns:
            List[Dict]: Firmen mit Job-Listings
        """
        max_jobs = self.config.get('maxJobsPerCompany', 3)

        for company in companies:
            existing_jobs = company.get('jobs', [])

            # Limitiere auf max_jobs
            company['jobs'] = existing_jobs[:max_jobs]

            # Optional: Scrape zusätzliche Jobs von Karriere-Seite
            career_url = company.get('career_url', '')
            if career_url and len(company['jobs']) < max_jobs:
                try:
                    additional_jobs = self.company_enricher.get_jobs_from_career_page(
                        career_url,
                        max_jobs=max_jobs - len(company['jobs'])
                    )

                    company['jobs'].extend(additional_jobs)

                except Exception as e:
                    logger.debug(f"Error scraping career page: {e}")

        return companies


async def main():
    """
    Apify Actor Main Function
    """
    async with Actor:
        # Lese Input
        actor_input = await Actor.get_input() or {}

        logger.info("Actor Input:")
        logger.info(actor_input)

        # Initialisiere Generator
        generator = B2BLeadGenerator(actor_input)

        # Führe Lead-Generierung durch
        leads = await generator.run()

        # Pushe zu Apify Dataset
        logger.info(f"\nPushing {len(leads)} leads to dataset...")
        await Actor.push_data(leads)

        # Optional: Exportiere als CSV
        try:
            csv_path = LeadExporter.export_to_csv(leads, 'leads_output.csv')
            logger.info(f"CSV exportiert: {csv_path}")

            # Optional: Als Key-Value Store speichern
            await Actor.set_value('OUTPUT_CSV', open(csv_path, 'r').read())

        except Exception as e:
            logger.error(f"CSV-Export fehlgeschlagen: {e}")

        logger.info("\n✓ Actor beendet erfolgreich")


if __name__ == "__main__":
    asyncio.run(main())
