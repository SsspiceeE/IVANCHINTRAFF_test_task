from aiogram import Router

from . import main

user_router = Router()
user_router.include_router(main.router)