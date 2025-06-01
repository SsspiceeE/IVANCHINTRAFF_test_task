import asyncio
import json
import logging
import os
import re
import tempfile
import zipfile
import traceback
import time
from typing import Dict, List, Tuple

from telethon import TelegramClient, types
from telethon.errors import FloodWaitError, SessionPasswordNeededError, PhoneCodeInvalidError

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
        old_client = None
        new_client = None
        new_session_path = None

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
                twofa_password = data.get("twoFA")

            proxy_type, host, port, username, proxy_password = proxy

            proxy_config = (
                proxy_type,
                host,
                port,
                True,
                username,
                proxy_password
            )

            account_logger.info(f"Using proxy: {username}@{host}:{port}")

            old_client = TelegramClient(
                session_path,
                api_id,
                api_hash,
                proxy=proxy_config,
                device_model="CheckBot",
                system_version="Linux",
                app_version="1.0",
                system_lang_code="en"
            )

            account_logger.info("Connecting to existing session...")
            await old_client.connect()
            account_logger.info("Connected to Telegram")

            authorized = await old_client.is_user_authorized()
            if not authorized:
                account_logger.warning("Account not authorized in existing session")
                return "error"

            new_session_path = f"{session_path}_new"
            account_logger.info(f"Creating new session at: {new_session_path}")

            new_client = TelegramClient(
                new_session_path,
                api_id,
                api_hash,
                proxy=proxy_config,
                device_model="CheckBot_NewSession",
                system_version="Linux",
                app_version="1.0",
                system_lang_code="en"
            )

            await new_client.connect()
            account_logger.info("New session client connected")

            account_logger.info("Requesting login code for new session")
            try:
                sent = await new_client.send_code_request(phone)
                phone_code_hash = sent.phone_code_hash
                account_logger.info("Login code requested")
            except FloodWaitError as fwe:
                account_logger.error(f"Flood wait error: {fwe}")
                return "error"

            account_logger.info("Waiting for verification code in existing session...")
            code = await self._wait_for_verification_code(old_client, account_logger)
            if not code:
                account_logger.error("Verification code not received")
                return "error"

            account_logger.info(f"Attempting sign-in with code: {code}")
            try:
                await new_client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash
                )
                account_logger.info("Successfully signed in to new session")
            except SessionPasswordNeededError:
                account_logger.info("2FA password required")
                if not twofa_password:
                    account_logger.error("2FA password not provided in JSON")
                    return "error"
                try:
                    await new_client.sign_in(password=twofa_password)
                    account_logger.info("Successfully signed in with 2FA")
                except Exception as e:
                    account_logger.error(f"2FA sign-in failed: {str(e)}")
                    return "error"
            except PhoneCodeInvalidError:
                account_logger.error("Invalid verification code")
                return "error"
            except Exception as e:
                account_logger.error(f"Sign-in failed: {str(e)}")
                return "error"

            account_logger.info("Checking spam status with new session")
            is_banned = await self._check_spam_status(new_client, account_logger)

            return "banned" if is_banned else "ok"

        except FloodWaitError as flood_wait_error:
            account_logger.error(f"FloodWait error: {flood_wait_error}")
            return "error"
        except Exception as exception:
            account_logger.error(f"Error during account processing: {str(exception)}")
            account_logger.error(traceback.format_exc())
            return "error"
        finally:
            if new_client and new_client.is_connected():
                account_logger.info("Disconnecting new session client")
                await new_client.disconnect()
            if old_client and old_client.is_connected():
                account_logger.info("Disconnecting existing session client")
                await old_client.disconnect()

    async def _wait_for_verification_code(
            self,
            client: TelegramClient,
            account_logger: logging.Logger,
            timeout: int = 30
    ) -> str:
        start_time = time.time()

        code_pattern = re.compile(r'\b(\d{5,6})\b')
        code_phrases = [
            "код", "code", "код подтверждения", "verification code",
            "confirmation code", "подтверждения", "проверки"
        ]
        senders = [777000, "SpamBot", "telegram"]

        while time.time() - start_time < timeout:
            waited = time.time() - start_time
            account_logger.info(f"Ожидание кода... Прошло {waited:.0f} сек")

            try:
                for sender in senders:
                    try:
                        messages = await client.get_messages(sender, limit=5)
                        account_logger.debug(f"Проверено сообщений от {sender}: {len(messages)}")

                        for msg in messages:
                            if msg.date.timestamp() < start_time:
                                continue

                            if msg.text:
                                account_logger.debug(f"Сообщение от {sender}: {msg.text[:50]}...")

                                match = code_pattern.search(msg.text)
                                if match:
                                    code = match.group(1)
                                    account_logger.info(f"Найден код подтверждения: {code}")
                                    return code

                                text_lower = msg.text.lower()
                                if any(phrase in text_lower for phrase in code_phrases):
                                    account_logger.info("Обнаружено сообщение с упоминанием кода")

                                    numbers = re.findall(r'\d{5,6}', msg.text)
                                    if numbers:
                                        code = numbers[0]
                                        account_logger.info(f"Извлечен код: {code}")
                                        return code
                                    else:
                                        account_logger.warning("Ключевые фразы найдены, но код не обнаружен")
                    except Exception as e:
                        account_logger.warning(f"Ошибка при проверке сообщений от {sender}: {str(e)}")

            except Exception as e:
                account_logger.warning(f"Общая ошибка при проверке сообщений: {str(e)}")

            await asyncio.sleep(10)

        account_logger.warning("Код подтверждения не получен в течение таймаута")
        return ""

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