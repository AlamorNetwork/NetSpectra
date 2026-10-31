import copy

import pytest
from pprl_core.qlog import SafeLogger, read_qlog


def sample():
    logger = SafeLogger()
    trace = logger.start_trace(True, b"private-connection-id")
    trace.log_event(
        category="transport",
        event="packet_received",
        data={
            "header": {"packet_type": "retry", "dcid": "SECRET"},
            "frames": [{"token": "SECRET", "headers": "SECRET"}],
            "raw": {"length": 1200, "data": "SECRET"},
        },
    )
    trace.log_event(category="http", event="frame_created", data={"headers": "SECRET"})
    return logger.export()


def test_qlog_projection_and_version_detection():
    document = sample()
    assert "SECRET" not in str(document) and "private-connection-id" not in str(
        document
    )
    assert read_qlog(document)["retry_packets"] == 1
    for version in ["0.4", "0.2", None]:
        with pytest.raises(ValueError, match="unsupported_qlog_version"):
            read_qlog(document | {"qlog_version": version})


@pytest.mark.parametrize(
    "mutation", ["headers", "timestamp", "nonfinite", "unknown", "address"]
)
def test_qlog_reader_rejects_unprojected_or_invalid_data(mutation):
    document = copy.deepcopy(sample())
    event = document["traces"][0]["events"][0]
    if mutation == "headers":
        event["data"]["headers"] = "secret"
    elif mutation == "timestamp":
        event["time"] = -1
    elif mutation == "nonfinite":
        event["time"] = float("nan")
    elif mutation == "unknown":
        event["name"] = "http:frame_created"
    else:
        document["traces"][0]["common_fields"]["address"] = "10.1.2.3"
    with pytest.raises(ValueError):
        read_qlog(document)


def test_qlog_has_a_hard_event_limit():
    logger = SafeLogger()
    trace = logger.start_trace(True, b"id")
    for _ in range(2010):
        trace.log_event(
            category="transport",
            event="packet_sent",
            data={"header": {"packet_type": "initial"}},
        )
    summary = read_qlog(logger.export())
    assert summary["event_count"] == 2000 and summary["limit_reached"]
