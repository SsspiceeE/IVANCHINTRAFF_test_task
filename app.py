import asyncio

from loader import dp, bot
from handlers import register_routers


async def main():
    register_routers(dp)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
