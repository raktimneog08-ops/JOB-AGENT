"""
Proxy rotation utility for the job aggregation agent.
Fetches free proxies from public lists, validates them, and provides rotation.
"""

import json
import random
import threading
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests

from utils.logger import get_logger

logger = get_logger()

# Free proxy list sources
PROXY_SOURCES = [
    "https://free-proxy-list.net/",
    "https://www.sslproxies.org/",
]

# Test URL and expected response for proxy validation
TEST_URL = "http://httpbin.org/ip"
TEST_TIMEOUT = 10  # seconds


class ProxyRotator:
    """
    Rotates through a pool of free proxies.
    Fetches proxies from public lists, validates them, and provides round-robin access.
    Falls back to direct connection if no proxies are available.
    """

    def __init__(
        self,
        validate_on_start: bool = True,
        cache_ttl_seconds: int = 1800,  # 30 minutes
        max_proxies: int = 20,
    ):
        self.cache_ttl = cache_ttl_seconds
        self.max_proxies = max_proxies
        self._proxies: List[dict] = []
        self._last_fetch_time: float = 0
        self._lock = threading.Lock()
        self._index = 0

        if validate_on_start:
            self.refresh_proxy_list()

    def _fetch_proxy_list(self) -> List[str]:
        """
        Fetch proxy list from public sources.
        Extracts IP:Port from HTML tables.

        Returns:
            List of "ip:port" strings
        """
        proxies = set()

        for source_url in PROXY_SOURCES:
            try:
                resp = requests.get(
                    source_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                    timeout=15,
                )
                resp.raise_for_status()

                # Parse HTML to find IP:Port in table rows
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(resp.text, "html.parser")
                table = soup.find("table", {"id": "proxylisttable"})
                if not table:
                    table = soup.find("table", class_="table")
                if not table:
                    # Try finding any table with proxy-like content
                    table = soup.find("table")

                if table:
                    for row in table.find_all("tr")[1:]:  # Skip header
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            ip = cols[0].get_text(strip=True)
                            port = cols[1].get_text(strip=True)
                            if ip and port and ip.count(".") == 3:
                                proxies.add(f"{ip}:{port}")

            except Exception as ex:
                logger.warning(f"Failed to fetch proxies from {source_url}: {ex}", module="ProxyRotator")

        return list(proxies)

    def _validate_proxy(self, proxy_str: str) -> Optional[dict]:
        """
        Test if a proxy is working by making a request through it.

        Args:
            proxy_str: "ip:port" string

        Returns:
            Proxy dict with 'http' and 'https' keys if valid, None otherwise
        """
        proxy_dict = {
            "http": f"http://{proxy_str}",
            "https": f"http://{proxy_str}",
        }

        try:
            resp = requests.get(
                TEST_URL,
                proxies=proxy_dict,
                timeout=TEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                proxy_ip = proxy_str.split(":")[0]
                if data.get("origin") and proxy_ip in data["origin"]:
                    return {
                        "proxy": proxy_dict,
                        "ip": proxy_ip,
                        "str": proxy_str,
                        "validated_at": time.time(),
                    }
        except Exception:
            pass

        return None

    def refresh_proxy_list(self) -> int:
        """
        Fetch and validate fresh proxies.

        Returns:
            Number of valid proxies found
        """
        with self._lock:
            raw_proxies = self._fetch_proxy_list()
            logger.info(
                f"Fetched {len(raw_proxies)} raw proxies, validating...",
                module="ProxyRotator",
            )

            valid_proxies = []
            for proxy_str in raw_proxies[:self.max_proxies * 3]:  # Test more than we need
                validated = self._validate_proxy(proxy_str)
                if validated:
                    valid_proxies.append(validated)
                    logger.debug(f"Valid proxy: {proxy_str}", module="ProxyRotator")
                if len(valid_proxies) >= self.max_proxies:
                    break

            self._proxies = valid_proxies
            self._last_fetch_time = time.time()
            self._index = 0

            logger.info(
                f"Proxy pool refreshed: {len(valid_proxies)} valid proxies",
                module="ProxyRotator",
            )
            return len(valid_proxies)

    def get_proxy(self) -> Optional[dict]:
        """
        Get the next working proxy in round-robin fashion.
        Refreshes the pool if cache is expired.

        Returns:
            Proxy dict with 'http' and 'https' keys, or None for direct connection
        """
        with self._lock:
            # Refresh if cache expired
            if time.time() - self._last_fetch_time > self.cache_ttl:
                logger.info("Proxy cache expired, refreshing...", module="ProxyRotator")
                self._proxies = []  # Clear while refreshing
                # Don't block - refresh in background
                threading.Thread(target=self.refresh_proxy_list, daemon=True).start()
                return None

            if not self._proxies:
                return None

            # Round-robin selection
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            return proxy["proxy"]

    def test_current_ip(self) -> str:
        """
        Get the current public IP (for debugging).

        Returns:
            IP address string
        """
        try:
            proxy = self.get_proxy()
            if proxy:
                resp = requests.get(TEST_URL, proxies=proxy, timeout=10)
            else:
                resp = requests.get(TEST_URL, timeout=10)
            return resp.json().get("origin", "unknown")
        except Exception as ex:
            return f"error: {ex}"

    @property
    def proxy_count(self) -> int:
        """Number of currently valid proxies."""
        with self._lock:
            return len(self._proxies)

    @property
    def is_available(self) -> bool:
        """Whether any proxies are currently available."""
        with self._lock:
            return len(self._proxies) > 0