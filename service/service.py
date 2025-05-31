import asyncio
import json
import logging
import os
import tempfile
import zipfile
import traceback
import time
from typing import Dict, List, Tuple

from telethon import TelegramClient, types
from telethon.errors import FloodWaitError, SessionPasswordNeededError

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

logger = logging.getLogger("service")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class Service:
    def __init__(self, proxies: List[str]):
        logger.info("Initializing Service with proxies")
        self.proxies = self._parse_proxies(proxies)
        if not self.proxies:
            logger.critical("No valid proxies in PROXY_LIST")
            raise RuntimeError("No valid proxies in PROXY_LIST")

        self.max_concurrent = 5
        logger.info(f"Service initialized with {len(self.proxies)} proxies, max concurrent: {self.max_concurrent}")

    def _parse_proxies(self, proxy_list: List[str]) -> List[tuple]:
        logger.info("Parsing proxies")
        valid_proxies = []
        for proxy_str in proxy_list:
            try:
                host, port_str, user, password = proxy_str.split(":")
                port = int(port_str)
                valid_proxies.append(("socks5", host, port, user, password))
                logger.debug(f"Added proxy: {host}:{port}")
            except (ValueError, TypeError) as exception:
                logger.error(f"Invalid proxy format: {proxy_str} - {str(exception)}")
        return valid_proxies

    async def check_accounts(self, zip_path: str) -> Dict[str, int]:
        start_time = time.time()
        logger.info(f"Starting accounts check for: {zip_path}")

        with tempfile.TemporaryDirectory() as temp_directory:
            logger.info(f"Created temporary directory: {temp_directory}")

            try:
                with zipfile.ZipFile(zip_path, 'r') as archive:
                    logger.info(f"Extracting archive: {zip_path}")
                    archive.extractall(temp_directory)
                    logger.info(f"Extracted {len(archive.namelist())} files")
            except zipfile.BadZipFile:
                logger.error("Invalid ZIP archive")
                raise ValueError("Invalid ZIP archive")

            pairs = self._find_account_pairs(temp_directory)
            if not pairs:
                logger.error("No valid account pairs found in archive")
                raise ValueError("No valid account pairs found in archive")

            logger.info(f"Found {len(pairs)} account pairs")
            results = await self._process_accounts(pairs)

        duration = time.time() - start_time
        logger.info(f"Accounts check completed in {duration:.2f} seconds")
        return self._compile_stats(results)

    def _find_account_pairs(self, folder: str) -> List[Tuple[str, str]]:
        logger.info(f"Finding account pairs in: {folder}")
        sessions = {}
        jsons = {}

        for root, _, files in os.walk(folder):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                lower_name = file_name.lower()

                if lower_name.endswith(".session"):
                    base = file_name[:-8]
                    sessions[base] = full_path
                    logger.debug(f"Found session: {full_path}")
                elif lower_name.endswith(".json"):
                    base = file_name[:-5]
                    jsons[base] = full_path
                    logger.debug(f"Found JSON: {full_path}")

        pairs = []
        for base, session_path in sessions.items():
            if base in jsons:
                json_path = jsons[base]
                pairs.append((session_path, json_path))
                logger.debug(f"Paired account: {session_path} with {json_path}")

        logger.info(f"Found {len(pairs)} valid account pairs")
        return pairs

    async def _process_accounts(self, pairs: List[Tuple[str, str]]) -> Dict[int, str]:
        logger.info(f"Processing {len(pairs)} accounts")
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results = {}

        async def process_one(index: int, session_path: str, json_path: str):
            start_time = time.time()
            account_logger = logging.getLogger(f"account_{index}")
            account_logger.setLevel(logging.INFO)
            account_logger.addHandler(handler)

            account_logger.info(f"Start processing account #{index}")
            account_logger.debug(f"Session: {session_path}, JSON: {json_path}")

            async with semaphore:
                proxy_index = index % len(self.proxies)
                proxy = self.proxies[proxy_index]
                account_logger.info(f"Using proxy #{proxy_index}: {proxy[1]}:{proxy[2]}")

                try:
                    status = await self._check_account(session_path, json_path, proxy, account_logger)
                except Exception as exception:
                    account_logger.error(f"Unhandled exception: {str(exception)}")
                    account_logger.error(traceback.format_exc())
                    status = "error"

                results[index] = status
                duration = time.time() - start_time
                account_logger.info(f"Account #{index} processed in {duration:.2f} seconds. Status: {status}")

        tasks = [
            process_one(index, session_path, json_path)
            for index, (session_path, json_path) in enumerate(pairs)
        ]
        await asyncio.gather(*tasks)
        return results

    async def _check_account(
            self,
            session_path: str,
            json_path: str,
            proxy: tuple,
            account_logger: logging.Logger
    ) -> str:
        try:
            account_logger.info("Loading account credentials")

            if not os.path.exists(json_path):
                account_logger.error(f"JSON file not found: {json_path}")
                return "error"

            with open(json_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

                if "api_id" in data:
                    api_id = int(data["api_id"])
                    api_hash = data["api_hash"]
                elif "app_id" in data:
                    api_id = int(data["app_id"])
                    api_hash = data["app_hash"]
                else:
                    account_logger.error("Missing API credentials in JSON file")
                    return "error"

                phone = data.get("phone", "")

            proxy_type, host, port, username, password = proxy

            proxy_config = (
                proxy_type,
                host,
                port,
                True,
                username,
                password
            )

            account_logger.info(f"Using proxy: {username}@{host}:{port}")

            client = TelegramClient(
                session_path,
                api_id,
                api_hash,
                proxy=proxy_config,
                device_model="CheckBot",
                system_version="Linux",
                app_version="1.0",
                system_lang_code="en"
            )

            account_logger.info("Connecting to Telegram...")
            await client.connect()
            account_logger.info("Connected to Telegram")

            account_logger.info("Checking authorization status")
            authorized = await client.is_user_authorized()
            account_logger.info(f"Authorization status: {authorized}")

            if not authorized:
                account_logger.warning("Account not authorized")
                return "error"

            account_logger.info("Checking spam status with @SpamBot")
            is_banned = await self._check_spam_status(client, account_logger)

            return "banned" if is_banned else "ok"

        except FloodWaitError as flood_wait_error:
            account_logger.error(f"FloodWait error: {flood_wait_error}")
            return "error"
        except SessionPasswordNeededError:
            account_logger.error("Two-factor authentication password needed")
            return "error"
        except Exception as exception:
            account_logger.error(f"Error during account check: {str(exception)}")
            account_logger.error(traceback.format_exc())
            return "error"
        finally:
            if 'client' in locals():
                account_logger.info("Disconnecting client")
                try:
                    await client.disconnect()
                    account_logger.info("Client disconnected")
                except Exception as disconnect_exception:
                    account_logger.error(f"Error disconnecting client: {str(disconnect_exception)}")

    async def _check_spam_status(self, client: TelegramClient, account_logger: logging.Logger) -> bool:
        try:
            account_logger.info("Getting @SpamBot entity")
            spam_bot = await client.get_entity("@SpamBot")
            account_logger.info("Sending /start to @SpamBot")
            await client.send_message(spam_bot, "/start")

            account_logger.info("Waiting for response from @SpamBot")
            try:
                messages = await asyncio.wait_for(
                    client.get_messages(spam_bot, limit=3),
                    timeout=45
                )
                account_logger.info(f"Received {len(messages)} messages from @SpamBot")
            except asyncio.TimeoutError:
                account_logger.warning("Timeout waiting for SpamBot response")
                return False

            if not messages:
                account_logger.warning("No messages received from SpamBot")
                return False

            full_text = "\n\n".join(
                message.text for message in messages
                if isinstance(message, types.Message) and message.text
            )

            if not full_text:
                account_logger.warning("No valid text in SpamBot response")
                return False

            account_logger.info(f"Full SpamBot response:\n{full_text}")

            lower_text = full_text.lower()

            # Расширенные фразы для детекции блокировок
            banned_phrases = [
                # Английские
                "spam ban",
                "restricted for spam",
                "under spam ban",
                "account is limited",
                "account was limited",
                "anti-spam systems",
                "harsh response",
                "submit a complaint",
                "you will not be able to send messages",
                "add them to groups",
                "phone contacts",
                "limited for spam",
                "spam block",
                "blocked for spam",

                # Русские
                "спам-бан",
                "заблокирован за спам",
                "ограничен за спам",
                "антиспам-систем",
                "не сможете отправлять сообщения",
                "добавлять их в группы",
                "номер в контактах",
                "аккаунт ограничен",
                "пожаловаться модераторам",
                "некоторые действия",
                "спам-блокировка",
                "лимитирован за спам"
            ]

            # Фразы для чистых аккаунтов
            clean_phrases = [
                # Английские
                "no restrictions",
                "not restricted",
                "account is free",
                "no limits",
                "without restrictions",
                "good standing",

                # Русские
                "аккаунт свободен",
                "не заблокирован",
                "нет ограничений",
                "без ограничений",
                "всё в порядке"
            ]

            # Детекция блокировки
            is_banned = any(phrase in lower_text for phrase in banned_phrases)

            # Детекция чистого аккаунта
            is_clean = any(phrase in lower_text for phrase in clean_phrases)

            if is_clean:
                account_logger.info("Spam status: OK (clean phrases detected)")
                return False

            if is_banned:
                account_logger.info("Spam status: BANNED (block phrases detected)")
                return True

            # Логируем неизвестный ответ
            account_logger.warning("Unknown SpamBot response. Marking as clean by default.")
            account_logger.debug(f"Unknown response text: {full_text}")
            return False

        except Exception as exception:
            account_logger.error(f"Error checking spam status: {str(exception)}")
            account_logger.error(traceback.format_exc())
            return False

    def _compile_stats(self, results: Dict[int, str]) -> Dict[str, int]:
        stats = {"total": len(results), "ok": 0, "banned": 0, "errors": 0}
        for status in results.values():
            if status == "ok":
                stats["ok"] += 1
            elif status == "banned":
                stats["banned"] += 1
            else:
                stats["errors"] += 1

        logger.info(
            f"Compiled statistics: Total={stats['total']}, "
            f"OK={stats['ok']}, Banned={stats['banned']}, Errors={stats['errors']}"
        )
        return stats


service = Service(PROXY_LIST)