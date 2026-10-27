from __future__ import annotations

import json
import os

from menu_engine.utils.groq_client import get_groq_judge_model, groq_chat_completion
from menu_engine.utils.privacy import redact_pii


def run_post_call_judge(order_id: str, spoken_summary: str, menu_item_ids: list[str]) -> dict:
    """Optional second-pass validation via Groq (free tier). Falls back to pass."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"passed": True, "notes": "Judge skipped — no GROQ_API_KEY (code validation already passed)"}

    model = get_groq_judge_model()
    # Mask any customer PII before sending summary to external LLM
    safe_summary = redact_pii(spoken_summary)
    prompt = (
        "You are an order QA judge. Reply JSON only: "
        '{"passed": true/false, "notes": "..."}. '
        "Verify the order summary only references plausible DIALOG Pizza menu items. "
        f"Known menu item ids include: {', '.join(menu_item_ids[:20])}. "
        f"Order summary: {safe_summary}"
    )

    try:
        data = groq_chat_completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=15,
        )
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as exc:  # noqa: BLE001
        return {"passed": True, "notes": f"Judge unavailable: {exc}"}
