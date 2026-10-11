"""ACIP payment-processor-sim: a config-driven simulated payment processor (docs/06 §2).

Exposes ``POST /v1/charge`` whose outcome (CAPTURED / DECLINED / simulated failure) and
latency are driven entirely by ``acip_common.config.Settings`` so the demo can show
approvals, declines, and processor failures without any real processor.
"""

from __future__ import annotations

__all__: list[str] = []
