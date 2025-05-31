import os

from aiogram import types, Router
from aiogram.filters.state import StateFilter
from aiogram.filters import CommandStart

from service.service import service
from filters.zip import IsZipFilter

router = Router()


@router.message(CommandStart(), StateFilter("*"))
async def bot_start(message: types.Message):
    await message.answer(f"Привет, {message.from_user.full_name}!")


@router.message(IsZipFilter())
async def handle_accounts(message: types.Message):
    document = message.document
    if not document.file_name.lower().endswith(".zip"):
        await message.answer("❗️ Пожалуйста, пришлите ZIP-архив с аккаунтами.")
        return

    await message.answer("🔄 Принят ZIP-архив. Начинаю проверку, это может занять несколько минут…")

    temp_zip = f"accounts_{message.from_user.id}.zip"

    file = await message.bot.get_file(document.file_id)
    await message.bot.download_file(file.file_path, destination=temp_zip)

    try:
        stats = await service.check_accounts(temp_zip)
        await message.answer(
            f"✅ Проверка завершена.\n"
            f"👥 Всего аккаунтов: <b>{stats['total']}</b>\n"
            f"🟢 Без спамблока: <b>{stats['ok']}</b>\n"
            f"🔴 Со спамблоком: <b>{stats['banned']}</b>\n"
            f"⚠️ Ошибок при проверке: <b>{stats['errors']}</b>",
            parse_mode="HTML"
        )
    except ValueError as ve:
        await message.answer(f"❌ Ошибка: {ve}")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при обработке архива.")
    finally:
        if os.path.exists(temp_zip):
            os.remove(temp_zip)
