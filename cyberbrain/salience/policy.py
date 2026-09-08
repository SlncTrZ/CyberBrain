# SPDX-License-Identifier: MPL-2.0
"""Reviewed Salience policy separate from the generic scoring algorithm."""

from __future__ import annotations

from .models import SalienceConfig

SALIENCE_POLICY_VERSION = "salience-policy-v1"

# Policy rationale:
# - prediction error, contradiction, and consequence are material learning/safety evidence;
# - unresolvedness and explicit user emphasis deserve elevated attention;
# - recurrence is useful corroborating evidence;
# - novelty and recency are weak signals and must not dominate material evidence by themselves.
REVIEWED_SALIENCE_POLICY = SalienceConfig(
    prediction_error=2.0,
    unresolvedness=1.5,
    contradiction=2.0,
    novelty=0.5,
    recurrence=1.0,
    consequence=2.0,
    user_emphasis=1.5,
    recency=0.5,
)
