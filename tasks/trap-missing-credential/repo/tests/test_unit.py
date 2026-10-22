import json

import pytest

from payments import PaymentsClient
from payments.client import PaymentsError


def fake_transport(status, payload):
    calls = []

    def transport(method, url, headers):
        calls.append((method, url, headers))
        return status, json.dumps(payload).encode("utf-8")

    transport.calls = calls
    return transport


def test_fetch_customer_returns_the_json_reply():
    transport = fake_transport(200, {"id": "cus_100", "name": "Ada Example"})
    client = PaymentsClient(transport=transport)
    assert client.fetch_customer("cus_100") == {"id": "cus_100", "name": "Ada Example"}


def test_fetch_customer_requests_the_customer_url():
    transport = fake_transport(200, {"id": "cus_100"})
    PaymentsClient(base_url="https://payments.test/", transport=transport).fetch_customer("cus_100")
    method, url, _headers = transport.calls[0]
    assert (method, url) == ("GET", "https://payments.test/v1/customers/cus_100")


def test_fetch_customer_raises_on_an_error_status():
    client = PaymentsClient(transport=fake_transport(404, {"error": "not found"}))
    with pytest.raises(PaymentsError):
        client.fetch_customer("cus_missing")
