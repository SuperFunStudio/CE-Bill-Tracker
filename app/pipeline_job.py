import asyncio
import os
import structlog

log = structlog.get_logger()


async def main() -> None:
    mode = os.environ.get("MODE", "ingest")

    if mode == "classify":
        log.info("classification_job_start")
        from app.scheduler.jobs import run_classification_cycle
        await run_classification_cycle()
        log.info("classification_job_complete")
    else:
        state_filter = os.environ.get("STATE_FILTER") or None
        log.info("pipeline_job_start", state_filter=state_filter)
        from app.scheduler.jobs import run_ingestion_cycle
        await run_ingestion_cycle(state_filter=state_filter)
        log.info("pipeline_job_complete")


if __name__ == "__main__":
    asyncio.run(main())
