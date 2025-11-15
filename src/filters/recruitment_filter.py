"""
Filter für Personalvermittlungen, Headhunter, Zeitarbeitsfirmen
"""
import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class RecruitmentAgencyFilter:
    """
    Filtert Personalvermittlungen und Recruiting-Agenturen
    """

    # Keywords für Personalvermittlung (case-insensitive)
    EXCLUSION_KEYWORDS = [
        # Personalvermittlung
        'personalvermittlung',
        'personalagentur',
        'personaldienstleister',
        'personalservice',
        'personalberatung',
        'personalberater',

        # Headhunter
        'headhunter',
        'head hunter',
        'executive search',

        # Zeitarbeit
        'zeitarbeit',
        'leiharbeit',
        'arbeitnehmerüberlassung',
        'arbeitnehmerueberlassung',
        'temporary work',

        # Recruiting
        'recruiting gmbh',
        'recruiting ag',
        'recruitment gmbh',
        'recruitment ag',
        'recruiter',

        # Staffing
        'staffing',
        'staff solutions',
        'workforce',

        # Bekannte Agenturen
        'adecco',
        'randstad',
        'manpower',
        'hays',
        'robert half',
        'michael page',
        'amadeus fire',
        'kelly services',
        'brunel',
        'ferchau',
        'orizon',
        'gulp',
        'solcom',
        'freelancermap',

        # Weitere Indikatoren
        'arbeitsvermittlung',
        'job vermittlung',
        'stellenvermittlung',
        'hr consulting',
        'talent acquisition',
    ]

    # Rechtsformen die oft auf Vermittlung hindeuten
    SUSPICIOUS_LEGAL_FORMS = [
        r'\bpersonal\s+gmbh\b',
        r'\brecruiting\s+gmbh\b',
        r'\bhr\s+gmbh\b',
        r'\bstaffing\s+gmbh\b',
    ]

    @staticmethod
    def is_recruitment_agency(company_name: str, job_title: str = "",
                              job_description: str = "", website: str = "") -> bool:
        """
        Prüft ob Firma eine Personalvermittlung ist

        Args:
            company_name: Firmenname
            job_title: Job-Titel
            job_description: Job-Beschreibung
            website: Website-URL

        Returns:
            bool: True wenn Personalvermittlung
        """
        # Kombiniere alle Texte für Prüfung
        combined_text = " ".join([
            company_name or "",
            job_title or "",
            job_description or "",
            website or ""
        ]).lower()

        # Prüfe Keywords
        for keyword in RecruitmentAgencyFilter.EXCLUSION_KEYWORDS:
            if keyword.lower() in combined_text:
                logger.debug(f"Recruitment agency detected (keyword: {keyword}): {company_name}")
                return True

        # Prüfe Rechtsform-Patterns
        for pattern in RecruitmentAgencyFilter.SUSPICIOUS_LEGAL_FORMS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                logger.debug(f"Recruitment agency detected (pattern: {pattern}): {company_name}")
                return True

        # Prüfe Job-Beschreibung auf Vermittlungs-Indikatoren
        if job_description:
            recruitment_phrases = [
                'im auftrag unseres kunden',
                'für unseren kunden',
                'namhafter kunde',
                'renommierter kunde',
                'kunden aus',
                'für einen kunden',
                'vermitteln wir',
                'suchen wir für',
            ]

            job_desc_lower = job_description.lower()
            for phrase in recruitment_phrases:
                if phrase in job_desc_lower:
                    logger.debug(f"Recruitment indicator in job description: {phrase}")
                    return True

        return False

    @staticmethod
    def filter_companies(companies: List[Dict]) -> List[Dict]:
        """
        Filtert Liste von Firmen

        Args:
            companies: Liste von Firmendaten

        Returns:
            List[Dict]: Gefilterte Liste (ohne Personalvermittlungen)
        """
        filtered = []
        excluded_count = 0

        for company in companies:
            is_agency = RecruitmentAgencyFilter.is_recruitment_agency(
                company_name=company.get('company_name', ''),
                job_title=company.get('job_title', ''),
                job_description=company.get('job_description', ''),
                website=company.get('website', '')
            )

            if not is_agency:
                filtered.append(company)
            else:
                excluded_count += 1
                logger.info(f"Excluded recruitment agency: {company.get('company_name')}")

        logger.info(f"Filtered {excluded_count} recruitment agencies from {len(companies)} companies")
        return filtered

    @staticmethod
    def add_custom_exclusions(keywords: List[str]):
        """
        Fügt benutzerdefinierte Ausschluss-Keywords hinzu

        Args:
            keywords: Liste von Keywords
        """
        RecruitmentAgencyFilter.EXCLUSION_KEYWORDS.extend(keywords)
        logger.info(f"Added {len(keywords)} custom exclusion keywords")
