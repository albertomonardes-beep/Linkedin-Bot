"""Scrapers package — import all portal scrapers here."""
from .trabajando import TrabajandoScraper
from .laborum import LaborumScraper
from .computrabajo import ComputrabajoScraper
from .linkedin import LinkedInScraper

__all__ = [
    "TrabajandoScraper",
    "LaborumScraper",
    "ComputrabajoScraper",
    "LinkedInScraper",
]
