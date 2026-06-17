"""Render TradingAgents output as HTML for Telegram attachment.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations

import html
from pathlib import Path

from app.schemas.alert import SIMULTANEOUS_ALERT_HINT, AlertType
from app.schemas.analysis import AnalysisResult
from app.services.analysis_report import extract_summary_excerpt


def _alert_label(alert_type: AlertType | None) -> str:
    if alert_type == AlertType.CLUSTER:
        return "均线密集-开仓机会"
    if alert_type == AlertType.TOUCH_200_MA:
        return "200MA 触碰-抄底机会"
    return "手动分析"


def build_summary(result: AnalysisResult) -> str:
    snap = result.job.snapshot
    trigger = _alert_label(snap.alert_type)
    if result.job.trigger.value == "manual":
        trigger = "手动 /analyze"

    decision_preview = extract_summary_excerpt(result.decision.strip())

    lines = [
        "🧠 *【AI 深度解读】*",
        f"`{snap.symbol}` · {snap.interval} · "
        f"触发：{trigger}",
        "",
        "📌 *Bot 快照*",
        f"现价 `${snap.price:,.2f}` · "
        f"200MA `${snap.ma_200:,.2f}`",
    ]
    if snap.cluster_pct is not None:
        lines.append(f"六线密集 `{snap.cluster_pct:.2f}%`")
    if snap.touch_ma_pct is not None and snap.touch_ma_side:
        lines.append(
            f"距200MA `{snap.touch_ma_pct:.2f}%` · "
            f"价格在200MA *{snap.touch_ma_side}*",
        )
    lines.extend(
        [
            "",
            "🎯 *结论摘要*",
            decision_preview,
            "",
            "📄 完整报告见下方 HTML 附件",
            SIMULTANEOUS_ALERT_HINT,
            "",
            f"_耗时 {result.elapsed_seconds:.0f}s · "
            f"{result.llm_provider} · {result.model}_",
        ],
    )
    return "\n".join(lines)


def write_html_report(
    result: AnalysisResult,
    reports_dir: Path,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    snap = result.job.snapshot
    stamp = result.job.requested_at.strftime("%Y%m%d_%H%M%S")
    safe_symbol = snap.symbol.replace("/", "_")
    filename = f"report_{safe_symbol}_{stamp}.html"
    path = reports_dir / filename

    trigger = _alert_label(snap.alert_type)
    if result.job.trigger.value == "manual":
        trigger = "手动 /analyze"

    body = html.escape(result.decision)
    snapshot_html = html.escape(
        f"标的: {snap.symbol}\n"
        f"周期: {snap.interval}\n"
        f"现价: {snap.price}\n"
        f"MA20/60/120/200: "
        f"{snap.ma_20:.2f} / {snap.ma_60:.2f} / "
        f"{snap.ma_120:.2f} / {snap.ma_200:.2f}\n"
        f"密集: {snap.cluster_pct}\n"
        f"距200MA: {snap.touch_ma_pct} ({snap.touch_ma_side})\n"
        f"触发: {trigger}",
    )

    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Invest Alert Bot · {html.escape(snap.symbol)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 900px; margin: 2rem auto; padding: 0 1rem;
      line-height: 1.6; color: #1a1a1a; background: #fafafa;
    }}
    h1 {{ font-size: 1.4rem; }}
    .meta, .disclaimer {{ color: #666; font-size: 0.9rem; }}
    pre {{
      white-space: pre-wrap; word-break: break-word;
      background: #fff; border: 1px solid #ddd; border-radius: 8px;
      padding: 1rem;
    }}
    .snapshot {{ background: #eef6ff; border-color: #b3d4fc; }}
    .decision {{ background: #fff; }}
  </style>
</head>
<body>
  <h1>🧠 AI 深度解读 · {html.escape(snap.symbol)}</h1>
  <p class="meta">
    周期 {html.escape(snap.interval)} ·
    触发 {html.escape(trigger)} ·
    {html.escape(result.llm_provider)} / {html.escape(result.model)} ·
    耗时 {result.elapsed_seconds:.1f}s
  </p>
  <h2>Bot 监控快照</h2>
  <pre class="snapshot">{snapshot_html}</pre>
  <h2>TradingAgents 分析</h2>
  <pre class="decision">{body}</pre>
  <p class="disclaimer">
    免责声明：本报告由 AI 自动生成，仅供研究参考，不构成任何投资建议。
    均线告警规则以 Invest Alert Bot 为准。仓位管理最重要，不输就是赢，
    不做投机只做投资。
  </p>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")
    return path
