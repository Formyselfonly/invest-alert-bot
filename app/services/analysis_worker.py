"""Background worker: run TradingAgents after alerts."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.analysis_env import AnalysisEnv
from app.notifiers.telegram import TelegramNotifier
from app.providers.tradingagents_client import TradingAgentsClient
from app.schemas.analysis import AnalysisJob
from app.services.report_html import build_summary, write_html_report

logger = logging.getLogger(__name__)


class AnalysisWorker:
    def __init__(
        self,
        settings: AnalysisEnv,
        notifier: TelegramNotifier,
    ) -> None:
        self._settings = settings
        self._notifier = notifier
        self._queue: asyncio.Queue[AnalysisJob | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._client = TradingAgentsClient(settings)
        self._reports_dir = Path(settings.reports_dir)

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    async def start(self) -> None:
        if not self.enabled:
            logger.info(
                "Analysis worker disabled (%s)",
                self._settings.status_label,
            )
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("Analysis worker started")

    async def stop(self) -> None:
        if self._task is None:
            return
        await self._queue.put(None)
        await self._task
        self._task = None
        logger.info("Analysis worker stopped")

    async def enqueue(self, job: AnalysisJob) -> None:
        if not self.enabled:
            logger.debug("Analysis skipped (disabled): %s", job.symbol)
            return
        await self._queue.put(job)
        logger.info(
            "Analysis queued: %s %s trigger=%s",
            job.symbol,
            job.snapshot.interval,
            job.trigger,
        )

    async def _loop(self) -> None:
        while True:
            job = await self._queue.get()
            if job is None:
                break
            try:
                await self._process(job)
            except TimeoutError:
                limit_min = self._settings.timeout_seconds // 60
                logger.exception(
                    "Analysis timed out for %s after %ss",
                    job.symbol,
                    self._settings.timeout_seconds,
                )
                await self._notifier.send_text(
                    f"⚠️ AI 分析超时 `{job.symbol}`\n"
                    f"已超过 {limit_min} 分钟上限。\n"
                    "可在 `.env` 调大 `ANALYSIS_TIMEOUT_SECONDS` 后重启 Bot。",
                )
            except Exception:
                logger.exception(
                    "Analysis failed for %s",
                    job.symbol,
                )
                await self._notifier.send_text(
                    f"⚠️ AI 分析失败 `{job.symbol}`\n"
                    "请检查 API Key 与日志。",
                )
            finally:
                self._queue.task_done()

    async def _process(self, job: AnalysisJob) -> None:
        trigger_label = job.trigger.value
        limit_min = max(3, self._settings.timeout_seconds // 60)
        await self._notifier.send_text(
            f"🧠 分析排队中… `{job.symbol}` · {job.snapshot.interval}\n"
            f"触发：{trigger_label} · 预计 3～{limit_min} 分钟",
        )

        result = await asyncio.wait_for(
            asyncio.to_thread(self._client.run, job),
            timeout=self._settings.timeout_seconds,
        )

        html_path = await asyncio.to_thread(
            write_html_report,
            result,
            self._reports_dir,
        )
        summary = build_summary(result)
        await self._notifier.send_analysis_report(summary, html_path)
        logger.info(
            "Analysis completed: %s in %.1fs -> %s",
            job.symbol,
            result.elapsed_seconds,
            html_path,
        )
