from __future__ import annotations

from app.core import error_reporting
from app.core.request_context import reset_request_id, set_request_id


def test_before_send_attaches_request_id():
    token = set_request_id("req-123")
    try:
        event = error_reporting._before_send({}, {})
    finally:
        reset_request_id(token)

    assert event["tags"]["request_id"] == "req-123"
    assert event["extra"]["request_id"] == "req-123"
