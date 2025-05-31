import asyncio
import json
import os
import tempfile
import zipfile
from typing import List, Tuple, Dict

from telethon import TelegramClient

PROXY_LIST = [
    "pool.infatica.io:10000:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10001:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10002:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10003:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10004:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10005:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10006:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10007:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10008:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10009:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10010:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10011:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10012:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10013:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10014:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10015:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10016:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10017:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10018:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10019:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10020:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10021:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
    "pool.infatica.io:10022:DpzAsXEwWPAxKnBCo9lu:RNW78Fm5",
]

class Service:
    def __init__(self, proxies: List[str]):
        self.proxies: List[Tuple[str, int, Tuple[str, str]]] = []
        for p in proxies:
            try:
                parsed = self._parse_proxy_string(p)
                self.proxies.append(parsed)
            except ValueError:
                continue

        if not self.proxies:
            raise RuntimeError("Нет валидных прокси в PROXY_LIST.")

        self.proxy_count = len(self.proxies)
        self.max_concurrent = 5

    def _parse_proxy_string(self, proxy_str: str) -> Tuple[str, int, Tuple[str, str]]:
        parts = proxy_str.split(":")
        if len(parts) != 4:
            raise ValueError(f"Неверный формат прокси: {proxy_str}")
        host, port_str, login, password = parts

        if not port_str.isdigit():
            raise ValueError(f"Порт не является числом в прокси: {proxy_str}")
        port = int(port_str)

        return host, port, (login, password)

    async def check_accounts(self, zip_path: str, user_id: int) -> Dict[str, int]:
        tmpdir = tempfile.TemporaryDirectory()
        extract_path = tmpdir.name

        with zipfile.ZipFile(zip_path, 'r') as archive:
            archive.extractall(extract_path)

        pairs = self._find_account_pairs(extract_path)
        if not pairs:
            tmpdir.cleanup()
            raise ValueError("В архиве не найдено ни одной пары .session + .json")

        results = await self._process_queue(pairs)

        tmpdir.cleanup()

        banned = sum(1 for v in results.values() if v == "banned")
        ok = sum(1 for v in results.values() if v == "ok")
        errors = sum(1 for v in results.values() if v == "error")

        return {
            "total": len(pairs),
            "banned": banned,
            "ok": ok,
            "errors": errors
        }

    def _find_account_pairs(self, folder: str) -> List[Tuple[str, str]]:
        sessions = {}
        jsons = {}
        for root, _, files in os.walk(folder):
            for fn in files:
                lower = fn.lower()
                if lower.endswith(".session"):
                    base = fn[:-8]
                    sessions[base] = os.path.join(root, fn)
                elif lower.endswith(".json"):
                    base = fn[:-5]
                    jsons[base] = os.path.join(root, fn)

        pairs: List[Tuple[str, str]] = []
        for base, ses_path in sessions.items():
            if base in jsons:
                pairs.append((ses_path, jsons[base]))
        return pairs

    async def _process_queue(self, pairs: List[Tuple[str, str]]) -> Dict[int, str]:
        queue = asyncio.Queue()
        results: Dict[int, str] = {}

        for idx, (session_path, json_path) in enumerate(pairs):
            proxy_idx = idx % self.proxy_count
            await queue.put((idx, session_path, json_path, proxy_idx))

        workers = [
            asyncio.create_task(self._worker(queue, results))
            for _ in range(min(self.max_concurrent, len(pairs)))
        ]

        await queue.join()
        for w in workers:
            w.cancel()

        return results

    async def _worker(self, queue: asyncio.Queue, results: dict):
        while True:
            try:
                idx, session_path, json_path, proxy_idx = await queue.get()
            except asyncio.CancelledError:
                break

            proxy_cfg = self.proxies[proxy_idx]
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    jd = json.load(f)
                    api_id = int(jd["api_id"])
                    api_hash = jd["api_hash"]

                is_banned = await self._check_single_account(session_path, api_id, api_hash, proxy_cfg)
                results[idx] = "banned" if is_banned else "ok"
            except Exception:
                results[idx] = "error"

            queue.task_done()

    async def _check_single_account(
        self,
        session_path: str,
        api_id: int,
        api_hash: str,
        proxy_cfg: Tuple[str, int, Tuple[str, str]]
    ) -> bool:
        host, port, (login, password) = proxy_cfg
        proxy = ("socks5", host, port, (login, password))

        client = TelegramClient(session_path, api_id, api_hash, proxy=proxy)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise Exception("Сессия не авторизована")

            try:
                entity = await client.get_entity("@SpamBot")
                await client.send_message(entity, "/start")
                response = await client.get_response("@SpamBot", timeout=10)
                text = response.text.lower()
            except Exception:
                return False

            if "не заблокирован" in text or "not under spam ban" in text:
                return False
            if "заблокирован" in text or "under spam ban" in text:
                return True

            return False
        finally:
            await client.disconnect()


service = Service(PROXY_LIST)
