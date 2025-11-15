"""Scraper-Module für Job-Portale"""

from .indeed_scraper import IndeedScraper
from .stepstone_scraper import StepStoneScraper
from .google_jobs_scraper import GoogleJobsScraper

__all__ = ['IndeedScraper', 'StepStoneScraper', 'GoogleJobsScraper']
