from aiogram import F, types
from aiogram.filters import Filter


class IsZipFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.document:
            return False
        file_name = message.document.file_name or ""
        return file_name.lower().endswith(".zip")