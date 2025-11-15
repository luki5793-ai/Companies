"""
Export-Funktionen für CSV/Excel-Output
"""
import csv
import logging
from datetime import datetime
from typing import List, Dict
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


class LeadExporter:
    """Exporter für Lead-Daten in CSV/Excel"""

    # Definiertes Output-Schema
    COLUMN_SCHEMA = [
        'Unternehmen',
        'Standort',
        'Webseiten_URL',
        'Anrede_AP1',
        'Vorname_AP1',
        'Nachname_AP1',
        'Email_AP1',
        'Telefon_AP1',
        'Position_AP1',
        'Anrede_AP2',
        'Vorname_AP2',
        'Nachname_AP2',
        'Email_AP2',
        'Telefon_AP2',
        'Position_AP2',
        'Job1_Titel',
        'Job1_URL',
        'Job2_Titel',
        'Job2_URL',
        'Job3_Titel',
        'Job3_URL',
        'Erfassungsdatum'
    ]

    @staticmethod
    def format_lead_data(company_data: Dict) -> Dict:
        """
        Formatiert Firmendaten nach Output-Schema

        Args:
            company_data: Roh-Firmendaten

        Returns:
            Dict: Formatierte Daten nach Schema
        """
        formatted = {col: '' for col in LeadExporter.COLUMN_SCHEMA}

        # Basis-Firmendaten
        formatted['Unternehmen'] = company_data.get('company_name', '')
        formatted['Standort'] = company_data.get('location', '')
        formatted['Webseiten_URL'] = company_data.get('website', '')
        formatted['Erfassungsdatum'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Kontakte (max 2)
        contacts = company_data.get('contacts', [])

        for idx, contact in enumerate(contacts[:2], start=1):
            prefix = f'AP{idx}'

            formatted[f'Anrede_{prefix}'] = contact.get('salutation', 'Herr/Frau')
            formatted[f'Vorname_{prefix}'] = contact.get('first_name', '')
            formatted[f'Nachname_{prefix}'] = contact.get('last_name', '')
            formatted[f'Email_{prefix}'] = contact.get('email', '')
            formatted[f'Telefon_{prefix}'] = contact.get('phone', '')
            formatted[f'Position_{prefix}'] = contact.get('position', '')

        # Jobs (max 3)
        jobs = company_data.get('jobs', [])

        for idx, job in enumerate(jobs[:3], start=1):
            formatted[f'Job{idx}_Titel'] = job.get('title', '')
            formatted[f'Job{idx}_URL'] = job.get('url', '')

        return formatted

    @staticmethod
    def export_to_csv(leads: List[Dict], output_path: str = 'leads.csv') -> str:
        """
        Exportiert Leads als CSV

        Args:
            leads: Liste von Lead-Daten
            output_path: Ausgabepfad

        Returns:
            str: Pfad zur erstellten Datei
        """
        if not leads:
            logger.warning("Keine Leads zum Exportieren")
            return None

        formatted_leads = [LeadExporter.format_lead_data(lead) for lead in leads]

        try:
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=LeadExporter.COLUMN_SCHEMA)
                writer.writeheader()
                writer.writerows(formatted_leads)

            logger.info(f"CSV exportiert: {output_path} ({len(leads)} Leads)")
            return output_path

        except Exception as e:
            logger.error(f"CSV-Export fehlgeschlagen: {e}")
            raise

    @staticmethod
    def export_to_excel(leads: List[Dict], output_path: str = 'leads.xlsx') -> str:
        """
        Exportiert Leads als Excel

        Args:
            leads: Liste von Lead-Daten
            output_path: Ausgabepfad

        Returns:
            str: Pfad zur erstellten Datei
        """
        if not leads:
            logger.warning("Keine Leads zum Exportieren")
            return None

        formatted_leads = [LeadExporter.format_lead_data(lead) for lead in leads]

        try:
            df = pd.DataFrame(formatted_leads, columns=LeadExporter.COLUMN_SCHEMA)

            # Excel mit Formatierung
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='B2B Leads')

                # Auto-width für Spalten
                worksheet = writer.sheets['B2B Leads']
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).apply(len).max(),
                        len(col)
                    )
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)

            logger.info(f"Excel exportiert: {output_path} ({len(leads)} Leads)")
            return output_path

        except Exception as e:
            logger.error(f"Excel-Export fehlgeschlagen: {e}")
            raise

    @staticmethod
    def validate_lead(lead_data: Dict) -> bool:
        """
        Validiert ob Lead Mindestanforderungen erfüllt

        Args:
            lead_data: Lead-Daten

        Returns:
            bool: True wenn valide
        """
        required_fields = [
            'company_name',
            'location',
            'website',
        ]

        # Prüfe Pflichtfelder
        for field in required_fields:
            if not lead_data.get(field):
                logger.warning(f"Lead ungültig: Fehlendes Feld '{field}'")
                return False

        # Mindestens 1 Kontakt erforderlich
        contacts = lead_data.get('contacts', [])
        if not contacts or len(contacts) == 0:
            logger.warning("Lead ungültig: Keine Kontakte")
            return False

        # Erster Kontakt muss E-Mail haben
        first_contact = contacts[0]
        if not first_contact.get('email'):
            logger.warning("Lead ungültig: Kein E-Mail bei Ansprechpartner 1")
            return False

        # Mindestens 1 Job erforderlich
        jobs = lead_data.get('jobs', [])
        if not jobs or len(jobs) == 0:
            logger.warning("Lead ungültig: Keine Jobs")
            return False

        return True

    @staticmethod
    def get_summary_statistics(leads: List[Dict]) -> Dict:
        """
        Generiert Zusammenfassungsstatistik

        Args:
            leads: Liste von Leads

        Returns:
            Dict: Statistiken
        """
        if not leads:
            return {}

        stats = {
            'total_companies': len(leads),
            'companies_with_2_contacts': 0,
            'companies_with_1_contact': 0,
            'total_contacts': 0,
            'total_jobs': 0,
            'avg_jobs_per_company': 0,
            'locations': set()
        }

        for lead in leads:
            contacts = lead.get('contacts', [])
            jobs = lead.get('jobs', [])

            contact_count = len(contacts)
            stats['total_contacts'] += contact_count

            if contact_count >= 2:
                stats['companies_with_2_contacts'] += 1
            elif contact_count == 1:
                stats['companies_with_1_contact'] += 1

            stats['total_jobs'] += len(jobs)

            location = lead.get('location', '')
            if location:
                stats['locations'].add(location)

        if stats['total_companies'] > 0:
            stats['avg_jobs_per_company'] = round(
                stats['total_jobs'] / stats['total_companies'], 2
            )

        stats['unique_locations'] = len(stats['locations'])
        stats['locations'] = list(stats['locations'])

        return stats
