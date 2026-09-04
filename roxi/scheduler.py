"""
Daily pipeline scheduler.

For each active subscription, schedules a daily run at the subscription's
delivery_hour in its delivery_timezone. Uses APScheduler with a SQLAlchemy
job store backed by a separate SQLite DB (scheduler.db) so jobs survive restarts.

Start from the FastAPI lifespan:
    from roxi.scheduler import start_scheduler, stop_scheduler
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

if TYPE_CHECKING:
    import types

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_SCHEDULER_DB = os.environ.get("ROXI_SCHEDULER_DB", "scheduler.db")

# How often (minutes) to re-sync active subscriptions to scheduler jobs
_SYNC_INTERVAL_MINUTES = 60


def start_scheduler(store_module: "types.ModuleType") -> None:
    """Initialise and start the APScheduler BackgroundScheduler.

    Args:
        store_module: The roxi.store module (or its Supabase replacement).
                      Passed in so callers control which backend is active.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        log.warning("scheduler.start_scheduler: already running — ignoring duplicate call")
        return

    jobstores = {
        "default": SQLAlchemyJobStore(url=f"sqlite:///{_SCHEDULER_DB}"),
    }

    _scheduler = BackgroundScheduler(jobstores=jobstores)

    # Perform an immediate sync, then re-sync every hour so new subscriptions
    # created via the API are picked up without a restart.
    _scheduler.add_job(
        _sync_jobs,
        trigger="interval",
        minutes=_SYNC_INTERVAL_MINUTES,
        args=[store_module],
        id="__sync_jobs__",
        name="Sync subscription jobs",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),  # run immediately on startup
    )

    _scheduler.start()
    log.info("scheduler: started (db=%s)", _SCHEDULER_DB)


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler — waits for running jobs to finish."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
        log.info("scheduler: stopped")
    _scheduler = None


def _sync_jobs(store_module: "types.ModuleType") -> None:
    """Read all active subscriptions and reconcile APScheduler jobs to match.

    - Adds a job for every active subscription that lacks one.
    - Removes jobs whose subscription has been paused or cancelled.
    - Updates the cron expression if delivery_hour / delivery_timezone changed.

    Safe to call repeatedly — all operations are idempotent.
    """
    if _scheduler is None or not _scheduler.running:
        log.warning("scheduler._sync_jobs: scheduler is not running")
        return

    try:
        subscriptions = store_module.list_active_subscriptions()
    except Exception as exc:
        log.error("scheduler._sync_jobs: failed to load subscriptions: %s", exc)
        return

    active_ids: set[str] = set()

    for sub in subscriptions:
        sub_id: str = sub["id"] if isinstance(sub, dict) else sub.id
        vertical_id: str = sub["vertical_id"] if isinstance(sub, dict) else sub.vertical_id
        delivery_hour: int = sub["delivery_hour"] if isinstance(sub, dict) else sub.delivery_hour
        delivery_tz: str = sub["delivery_timezone"] if isinstance(sub, dict) else sub.delivery_timezone
        paused: bool = sub["paused"] if isinstance(sub, dict) else sub.paused
        status: str = sub["status"] if isinstance(sub, dict) else sub.status

        job_id = f"sub_{sub_id}"
        active_ids.add(job_id)

        if paused or status != "active":
            # Remove any existing job for this subscription
            if _scheduler.get_job(job_id):
                _scheduler.remove_job(job_id)
                log.info("scheduler: removed job %s (status=%s paused=%s)", job_id, status, paused)
            continue

        existing = _scheduler.get_job(job_id)
        trigger = CronTrigger(
            hour=delivery_hour,
            minute=0,
            timezone=delivery_tz,
        )

        if existing is None:
            _scheduler.add_job(
                _run_subscription,
                trigger=trigger,
                args=[sub_id],
                id=job_id,
                name=f"Pipeline: {vertical_id} ({sub_id[:8]})",
                replace_existing=True,
            )
            log.info(
                "scheduler: added job %s for vertical=%s at hour=%d tz=%s",
                job_id, vertical_id, delivery_hour, delivery_tz,
            )
        else:
            # Check whether cron parameters changed; replace if so.
            # APScheduler stores trigger args; easiest to compare via string repr.
            existing_trigger_str = str(existing.trigger)
            new_trigger_str = str(trigger)
            if existing_trigger_str != new_trigger_str:
                _scheduler.reschedule_job(job_id, trigger=trigger)
                log.info(
                    "scheduler: rescheduled job %s (hour=%d tz=%s)",
                    job_id, delivery_hour, delivery_tz,
                )

    # Remove orphaned jobs (subscriptions that no longer exist or were deleted)
    for job in _scheduler.get_jobs():
        if job.id.startswith("sub_") and job.id not in active_ids:
            _scheduler.remove_job(job.id)
            log.info("scheduler: pruned orphaned job %s", job.id)

    log.debug("scheduler._sync_jobs: synced %d subscriptions", len(subscriptions))


def _run_subscription(subscription_id: str) -> None:
    """Execute the full pipeline for one subscription.

    Loads vertical config (from DB rules or YAML fallback), checks the spend
    ceiling, then delegates to pipeline.run(). All errors are caught and logged
    so a single failed subscription never crashes the scheduler thread.
    """
    # Import lazily so the scheduler module can be imported without triggering
    # the full dependency graph at process start.
    from roxi import store as _store
    from roxi import pipeline

    log.info("scheduler: starting run for subscription %s", subscription_id)

    try:
        sub_row = _store.get_subscription(subscription_id)
    except AttributeError:
        # store.get_subscription may not exist in the SQLite backend yet;
        # fall back to listing all and filtering.
        try:
            all_subs = _store.list_active_subscriptions()
            sub_row = next(
                (s for s in all_subs if (s["id"] if isinstance(s, dict) else s.id) == subscription_id),
                None,
            )
        except Exception as exc:
            log.error("scheduler: could not load subscription %s: %s", subscription_id, exc)
            return

    if sub_row is None:
        log.warning("scheduler: subscription %s not found — skipping", subscription_id)
        return

    if isinstance(sub_row, dict):
        org_id = sub_row.get("org_id")
        spend_ceiling = float(sub_row.get("spend_ceiling_usd", 5.0))
        vertical_id = sub_row.get("vertical_id", "")
        rules_version_id = sub_row.get("rules_version_id")
    else:
        org_id = sub_row.org_id
        spend_ceiling = float(sub_row.spend_ceiling_usd)
        vertical_id = sub_row.vertical_id
        rules_version_id = sub_row.rules_version_id

    # Spend ceiling check: sum today's LLM costs for this org
    try:
        today_cost = _store.get_today_cost(org_id=org_id)
    except AttributeError:
        # Fallback: check via daily_costs if get_today_cost not available
        try:
            daily = _store.daily_costs(days=1, vertical_id=vertical_id)
            today_cost = daily[0]["cost_usd"] if daily else 0.0
        except Exception:
            today_cost = 0.0

    if today_cost >= spend_ceiling:
        log.warning(
            "scheduler: subscription %s (org=%s) already at spend ceiling "
            "$%.4f >= $%.4f — skipping today's run",
            subscription_id, org_id, today_cost, spend_ceiling,
        )
        return

    try:
        vertical_config = _load_vertical_config(sub_row)
    except Exception as exc:
        log.error(
            "scheduler: failed to load vertical config for subscription %s: %s",
            subscription_id, exc,
        )
        return

    try:
        leads = pipeline.run(vertical_config, org_id=org_id)
        log.info(
            "scheduler: run complete for subscription %s — %d lead(s) delivered",
            subscription_id, len(leads),
        )
    except Exception as exc:
        log.error(
            "scheduler: pipeline.run failed for subscription %s: %s",
            subscription_id, exc, exc_info=True,
        )


def _load_vertical_config(sub_row: dict | object) -> "VerticalConfig":
    """Build a VerticalConfig for the given subscription.

    If the subscription has a rules_version_id, loads the VerticalRules record
    from the store and constructs a VerticalConfig from it. Otherwise falls back
    to the YAML file at verticals/<vertical_id>.yaml.

    Args:
        sub_row: A dict or Pydantic Subscription object.

    Returns:
        A fully-populated VerticalConfig ready for pipeline.run().

    Raises:
        FileNotFoundError: If YAML fallback path does not exist.
        ValueError: If rules_json or icp_json are malformed.
    """
    from roxi.config import (
        VerticalConfig,
        ICPConfig,
        ScoringRule,
        ChannelsConfig,
        ModelsConfig,
        load_vertical,
    )
    from roxi import store as _store

    if isinstance(sub_row, dict):
        vertical_id = sub_row["vertical_id"]
        rules_version_id = sub_row.get("rules_version_id")
        daily_research_budget = int(sub_row.get("daily_research_budget", 15))
        qualify_threshold = int(sub_row.get("qualify_threshold", 70))
    else:
        vertical_id = sub_row.vertical_id
        rules_version_id = sub_row.rules_version_id
        daily_research_budget = int(sub_row.daily_research_budget)
        qualify_threshold = int(sub_row.qualify_threshold)

    if rules_version_id:
        # Load rules from DB
        try:
            rules_row = _store.get_vertical_rules(rules_version_id)
        except AttributeError:
            rules_row = None

        if rules_row is None:
            log.warning(
                "scheduler._load_vertical_config: rules_version_id=%s not found, "
                "falling back to YAML for vertical=%s",
                rules_version_id, vertical_id,
            )
        else:
            if isinstance(rules_row, dict):
                rules_json = rules_row.get("rules_json", "[]")
                icp_json = rules_row.get("icp_json", "{}")
                product_brief = rules_row.get("product_brief", "")
            else:
                rules_json = rules_row.rules_json
                icp_json = rules_row.icp_json
                product_brief = rules_row.product_brief

            try:
                raw_rules = json.loads(rules_json)
                raw_icp = json.loads(icp_json)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed JSON in VerticalRules {rules_version_id}: {exc}"
                ) from exc

            scoring_rules = [ScoringRule.model_validate(r) for r in raw_rules]
            icp = ICPConfig.model_validate(raw_icp)

            return VerticalConfig(
                vertical_id=vertical_id,
                product_brief=product_brief,
                icp=icp,
                scoring_rules=scoring_rules,
                qualify_threshold=qualify_threshold,
                channels=ChannelsConfig(),
                models=ModelsConfig(),
                daily_research_budget=daily_research_budget,
            )

    # YAML fallback
    yaml_paths = [
        f"verticals/{vertical_id}.yaml",
        f"verticals/{vertical_id}.yml",
        f"{vertical_id}.yaml",
    ]
    for path in yaml_paths:
        if os.path.exists(path):
            cfg = load_vertical(path)
            # Override per-subscription thresholds so the DB values take precedence
            cfg = cfg.model_copy(update={
                "qualify_threshold": qualify_threshold,
                "daily_research_budget": daily_research_budget,
            })
            return cfg

    raise FileNotFoundError(
        f"No YAML vertical config found for {vertical_id!r}. "
        f"Tried: {yaml_paths}. Set rules_version_id on the subscription to use DB-stored rules."
    )
