"""Referenzprojekt fuer Kapitel 24."""

from .models import DocumentInput, PublicationProposal
from .service import DocumentReleaseService

__all__ = ["DocumentInput", "DocumentReleaseService", "PublicationProposal"]
