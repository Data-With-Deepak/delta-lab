"""
Minimal Delta Exchange (India) REST client.

Handles both public (unauthenticated) and private (HMAC-signed) endpoints.

Signing scheme per Delta docs:
    signature = HMAC_SHA256(secret, method + timestamp + path + query + body)  -> hex
    headers:   api-key, signature, timestamp (unix seconds), User-Agent
The signature must reach Delta within ~5 seconds, so we sign right before sending.
"""

import hashlib
import hmac
import json
import time

import requests

# Base URLs. Choose with DeltaClient(env="prod" | "testnet").
BASE_URLS = {
    "prod": "https://api.india.delta.exchange",
    "testnet": "https://cdn-ind.testnet.deltaex.org",
}

USER_AGENT = "delta-lab/0.1 (python-requests)"


class DeltaError(Exception):
    """Raised when Delta returns an error payload or a non-2xx response."""


class DeltaClient:
    def __init__(self, api_key=None, api_secret=None, env="prod", timeout=10):
        if env not in BASE_URLS:
            raise ValueError(f"env must be one of {list(BASE_URLS)}")
        self.base_url = BASE_URLS[env]
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.session = requests.Session()

    # ---- internals -------------------------------------------------------
    def _sign(self, method, path, query="", body=""):
        if not (self.api_key and self.api_secret):
            raise DeltaError("This endpoint needs API key + secret. Set them in .env")
        timestamp = str(int(time.time()))
        message = method + timestamp + path + query + body
        signature = hmac.new(
            self.api_secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return {
            "api-key": self.api_key,
            "signature": signature,
            "timestamp": timestamp,
            "User-Agent": USER_AGENT,
        }

    def _request(self, method, path, params=None, body=None, auth=False):
        url = self.base_url + path
        query = ""
        if params:
            # requests builds the query; we must sign the SAME string (with leading '?')
            query = "?" + requests.models.RequestEncodingMixin._encode_params(params)
        body_str = json.dumps(body) if body else ""

        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if auth:
            headers.update(self._sign(method, path, query, body_str))
        if body:
            headers["Content-Type"] = "application/json"

        resp = self.session.request(
            method, url, params=params, data=body_str or None,
            headers=headers, timeout=self.timeout,
        )
        try:
            data = resp.json()
        except ValueError:
            raise DeltaError(f"{resp.status_code}: non-JSON response: {resp.text[:200]}")
        if not resp.ok or (isinstance(data, dict) and data.get("success") is False):
            raise DeltaError(f"{resp.status_code}: {json.dumps(data)[:300]}")
        return data

    # ---- public endpoints ------------------------------------------------
    def get_products(self, contract_types=None):
        """All tradable instruments. contract_types e.g. 'perpetual_futures,call_options'."""
        params = {"contract_types": contract_types} if contract_types else None
        return self._request("GET", "/v2/products", params=params)

    def get_tickers(self, contract_types=None):
        params = {"contract_types": contract_types} if contract_types else None
        return self._request("GET", "/v2/tickers", params=params)

    def get_ticker(self, symbol):
        return self._request("GET", f"/v2/tickers/{symbol}")

    def get_candles(self, symbol, resolution, start, end):
        """OHLCV. resolution e.g. '1m','5m','1h','1d'. start/end = unix seconds."""
        params = {"symbol": symbol, "resolution": resolution,
                  "start": start, "end": end}
        return self._request("GET", "/v2/history/candles", params=params)

    def get_assets(self):
        return self._request("GET", "/v2/assets")

    def get_orderbook(self, symbol):
        """L2 order book: result.buy (bids) and result.sell (asks)."""
        return self._request("GET", f"/v2/l2orderbook/{symbol}")

    def get_trades(self, symbol):
        """Recent public trades. Each has size, price, buyer_role/seller_role
        (whichever is 'taker' is the aggressor)."""
        return self._request("GET", f"/v2/trades/{symbol}")

    # ---- private endpoints (need API key) --------------------------------
    def get_balances(self):
        return self._request("GET", "/v2/wallet/balances", auth=True)

    def get_positions(self):
        return self._request("GET", "/v2/positions/margined", auth=True)

    def get_open_orders(self):
        return self._request("GET", "/v2/orders", params={"state": "open"}, auth=True)
