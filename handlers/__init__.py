from aiogram import Dispatcher
from .users import user_router


def register_routers(dp: Dispatcher):
    dp.include_router(user_router)