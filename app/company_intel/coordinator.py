"""Company Intel Coordinator.

Orchestrates all three company data enrichment sources in sequence:
  1. EPA FRS     — validate Oregon facility presence
  2. CAA Registry — confirm obligated party status
  3. SEC EDGAR   — enrich material volume data from 10-K filings

Each source pipes candidates through the EntityResolver before touching the DB.
All enrichment modifies existing Company/CompanyMaterial/CompanyStatePresence records
or queues unresolved candidates in entity_match_queue for manual review.

Usage:
    coordinator = CompanyIntelCoordinator()
    stats = await coordinator.refresh_all(db)
    await db.commit()
"""
from typing import Any

import structlog

log = structlog.get_logger()


class CompanyIntelCoordinator:
    """Orchestrates company intel ingestion sources."""

    async def refresh_all(self, db: Any) -> dict:
        """Run EPA FRS -> CAA registry -> SEC EDGAR in sequence.

        Returns a combined stats dict. Each source's stats are nested under
        its key (epa_frs, caa_registry, sec_edgar) plus a top-level summary.
        """
        from app.company_intel.epa_frs import run_epa_frs_enrichment
        from app.company_intel.sec_edgar import run_sec_edgar_enrichment
        from app.company_intel.state_registries import run_caa_registry_enrichment

        log.info("company_intel_refresh_start")

        # Step 1: EPA FRS — facility-level validation
        log.info("company_intel_step", step="epa_frs")
        try:
            epa_stats = await run_epa_frs_enrichment(db)
        except Exception as exc:
            log.error("company_intel_epa_frs_error", error=str(exc))
            epa_stats = {"error": str(exc)}

        # Step 2: CAA Registry — confirmed obligated parties
        log.info("company_intel_step", step="caa_registry")
        try:
            caa_stats = await run_caa_registry_enrichment(db)
        except Exception as exc:
            log.error("company_intel_caa_registry_error", error=str(exc))
            caa_stats = {"error": str(exc)}

        # Step 3: SEC EDGAR — volume enrichment (runs last so entity resolution is settled)
        log.info("company_intel_step", step="sec_edgar")
        try:
            edgar_stats = await run_sec_edgar_enrichment(db)
        except Exception as exc:
            log.error("company_intel_sec_edgar_error", error=str(exc))
            edgar_stats = {"error": str(exc)}

        combined = {
            "epa_frs": epa_stats,
            "caa_registry": caa_stats,
            "sec_edgar": edgar_stats,
            # Top-level summary for scheduler log
            "total_state_presences_added": epa_stats.get("state_presences_added", 0),
            "total_caa_matched": caa_stats.get("matched", 0),
            "total_caa_unmatched": caa_stats.get("unmatched", 0),
            "total_volumes_updated": edgar_stats.get("volumes_updated", 0),
        }

        log.info("company_intel_refresh_complete", **{k: v for k, v in combined.items() if not isinstance(v, dict)})
        return combined
