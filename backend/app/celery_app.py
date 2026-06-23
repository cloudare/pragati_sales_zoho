"""
Celery app and scheduled tasks.

Tasks:
  drain_tally_queue       - every 15 minutes
  zoho_items_sync         - every 6 hours
  zoho_contacts_sync      - every 6 hours
  eod_full_sync           - daily at 23:30 (end-of-day per PRD)

For dev without Redis, set CELERY_EAGER=true to run tasks inline.

For production:
  worker:  celery -A app.celery_app worker -l info
  beat:    celery -A app.celery_app beat -l info
"""
import logging
from celery import Celery
from celery.schedules import crontab

from .core.config import settings

log = logging.getLogger(__name__)

broker = settings.celery_broker_url or settings.redis_url
backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery("pragati", broker=broker, backend=backend)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_always_eager=settings.celery_eager,
    task_eager_propagates=settings.celery_eager,
    beat_schedule={
        "drain-tally-every-15min": {
            "task": "app.celery_app.drain_tally_queue",
            "schedule": 15 * 60,  # seconds
        },
        "zoho-items-sync": {
            "task": "app.celery_app.zoho_items_sync",
            "schedule": 6 * 60 * 60,
        },
        "zoho-contacts-sync": {
            "task": "app.celery_app.zoho_contacts_sync",
            "schedule": 6 * 60 * 60,
        },
        "eod-full-sync": {
            "task": "app.celery_app.eod_full_sync",
            "schedule": crontab(hour=23, minute=30),  # 23:30 IST daily
        },
    },
)


def _with_db(fn):
    """Run a function with a fresh DB session."""
    from .core.database import SessionLocal
    db = SessionLocal()
    try:
        return fn(db)
    finally:
        db.close()


@celery_app.task(name="app.celery_app.drain_tally_queue")
def drain_tally_queue():
    """Drain pending items in the Tally outbound queue."""
    from .services.tally_outbound import drain_outbound_queue
    result = _with_db(drain_outbound_queue)
    log.info("drain_tally_queue: %s", result)
    return result


@celery_app.task(name="app.celery_app.zoho_items_sync")
def zoho_items_sync():
    from .services.zoho_master_sync import sync_items
    result = _with_db(sync_items)
    log.info("zoho_items_sync: %s", result)
    return result


@celery_app.task(name="app.celery_app.zoho_contacts_sync")
def zoho_contacts_sync():
    from .services.zoho_master_sync import sync_contacts
    result = _with_db(sync_contacts)
    log.info("zoho_contacts_sync: %s", result)
    return result


@celery_app.task(name="app.celery_app.eod_full_sync")
def eod_full_sync():
    """End-of-day full sync per PRD M14."""
    items = zoho_items_sync.run() if settings.celery_eager else zoho_items_sync.delay()
    contacts = zoho_contacts_sync.run() if settings.celery_eager else zoho_contacts_sync.delay()
    queue = drain_tally_queue.run() if settings.celery_eager else drain_tally_queue.delay()
    return {"items": str(items), "contacts": str(contacts), "queue": str(queue)}
