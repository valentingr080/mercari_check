# scrapers/base.py
from __future__ import annotations
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass(frozen=True)
class Product:
    id: str
    url: str
    price: str
    image: str | None = None
    extra: dict | None = None


class Scraper(ABC):
    """
    A scraper returns Product objects from its source.
    """

    @property
    @abstractmethod
    def source(self) -> str: ...

    @abstractmethod
    def fetch(self) -> list[Product]: ...
