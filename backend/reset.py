import asyncio
from app.database import AsyncSessionLocal
from app.models import User
from sqlalchemy import update
from app.auth.jwt import hash_password

async def main():
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.email == 'fakhirbaig27@gmail.com').values(password_hash=hash_password('password123')))
        await session.commit()
    print('Password updated')

if __name__ == '__main__':
    asyncio.run(main())
