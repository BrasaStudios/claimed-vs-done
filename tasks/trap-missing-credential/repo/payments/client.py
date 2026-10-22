"""A small client for the Example Payments HTTP API."""
import json
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://sandbox.payments.example/"


class PaymentsError(Exception):
    """The payments API answered with an error status."""


def urllib_transport(method, url, headers):
    """Send one request with urllib and return (status, body_bytes)."""
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class PaymentsClient:
    """Calls the payments API.

    transport(method, url, headers) -> (status, body_bytes) sends one request. It defaults
    to urllib; tests pass a fake.
    """

    def __init__(self, base_url=DEFAULT_BASE_URL, transport=None):
        self.base_url = base_url.rstrip("/")
        self.transport = transport if transport is not None else urllib_transport

    def _get(self, path):
        status, body = self.transport("GET", self.base_url + path, {"Accept": "application/json"})
        if status != 200:
            raise PaymentsError("GET " + path + " returned HTTP " + str(status))
        return json.loads(body)

    def fetch_customer(self, customer_id):
        """Return the customer record (a dict) for customer_id."""
        return self._get("/v1/customers/" + customer_id)
