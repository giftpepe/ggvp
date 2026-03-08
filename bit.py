"""
GiftPepe Bot - Telegram Mini App Bot
Пополнение через Stars (инвойсы), реферальная система
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery, 
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, LabeledPrice, ContentType
)
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from supabase import create_client

# ===== CONFIG =====
BOT_TOKEN = "7948801307:AAEVkGlfE4kd0dmgifPZPdQb4FK3vvXrdUc"
WEBAPP_URL = "https://giftpepe.github.io"
ADMIN_ID = 8339935446

# Supabase
SUPABASE_URL = "https://soxzsdwtutwdzygezsnk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNveHpzZHd0dXR3ZHp5Z2V6c25rIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjg2NzMwNywiZXhwIjoyMDg4NDQzMzA3fQ.VvVJW7abALCE0vPXU1gebKEf1JJhk8-Owk0b-VYK6jQ"

# Курс: 100 Stars = 1.1 TON
STARS_TO_TON_RATE = 1.1 / 100

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


async def get_or_create_user(user_id: int, username: str = None, first_name: str = None):
    """Получить или создать пользователя"""
    try:
        result = supabase.table("users").select("*").eq("id", user_id).execute()
        if result.data:
            return result.data[0]
        
        # Создаём нового пользователя
        new_user = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "balance": 0,
            "referral_count": 0,
            "referral_earnings": 0
        }
        supabase.table("users").insert(new_user).execute()
        return new_user
    except Exception as e:
        logger.error(f"DB error: {e}")
        return None


async def update_balance(user_id: int, amount: float):
    """Обновить баланс пользователя"""
    try:
        result = supabase.table("users").select("balance").eq("id", user_id).execute()
        if result.data:
            current = result.data[0].get("balance", 0) or 0
            new_balance = current + amount
            supabase.table("users").update({"balance": new_balance}).eq("id", user_id).execute()
            return new_balance
        return None
    except Exception as e:
        logger.error(f"Update balance error: {e}")
        return None


async def process_referral_bonus(user_id: int, amount: float):
    """Начислить реферальный бонус (10% от пополнения)"""
    try:
        result = supabase.table("users").select("referrer_id").eq("id", user_id).execute()
        if result.data and result.data[0].get("referrer_id"):
            referrer_id = result.data[0]["referrer_id"]
            bonus = amount * 0.10  # 10%
            
            # Получаем текущие данные реферера
            ref_result = supabase.table("users").select("balance, referral_earnings").eq("id", referrer_id).execute()
            if ref_result.data:
                current_balance = ref_result.data[0].get("balance", 0) or 0
                current_earnings = ref_result.data[0].get("referral_earnings", 0) or 0
                
                supabase.table("users").update({
                    "balance": current_balance + bonus,
                    "referral_earnings": current_earnings + bonus
                }).eq("id", referrer_id).execute()
                
                # Уведомляем реферера
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🎉 <b>Реферальный бонус!</b>\n\n"
                        f"Ваш реферал пополнил баланс.\n"
                        f"Ваш бонус: <b>+{bonus:.2f} TON</b> (10%)",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
                
                return bonus
    except Exception as e:
        logger.error(f"Referral bonus error: {e}")
    return 0


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка /start"""
    user = message.from_user
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    
    # Создаём пользователя
    await get_or_create_user(user.id, user.username, user.first_name)
    
    # Обработка реферальной ссылки
    if args and args.startswith("ref_"):
        try:
            referrer_id = int(args.replace("ref_", ""))
            if referrer_id != user.id:
                # Проверяем что у пользователя ещё нет реферера
                result = supabase.table("users").select("referrer_id").eq("id", user.id).execute()
                if result.data and not result.data[0].get("referrer_id"):
                    # Устанавливаем реферера
                    supabase.table("users").update({"referrer_id": referrer_id}).eq("id", user.id).execute()
                    
                    # Увеличиваем счётчик рефералов
                    ref_result = supabase.table("users").select("referral_count").eq("id", referrer_id).execute()
                    if ref_result.data:
                        count = ref_result.data[0].get("referral_count", 0) or 0
                        supabase.table("users").update({"referral_count": count + 1}).eq("id", referrer_id).execute()
                    
                    # Уведомляем реферера
                    try:
                        await bot.send_message(
                            referrer_id,
                            f"🎉 <b>Новый реферал!</b>\n\n"
                            f"По вашей ссылке зарегистрировался новый пользователь.\n"
                            f"Вы получите 10% от его пополнений!",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
        except:
            pass
    
    # Обработка оплаты Stars
    if args and args.startswith("pay_"):
        try:
            stars = int(args.replace("pay_", ""))
            if stars >= 1:
                await send_stars_invoice(message, stars)
                return
        except:
            pass
    
    # Обычный старт — показываем описание и кнопку играть
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎮 Играть",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])
    
    await message.answer(
        f"🎁 <b>Добро пожаловать в GiftPepe!</b>\n\n"
        f"🎰 Открывай кейсы с NFT-подарками\n"
        f"🔄 Апгрейди подарки и получай редкие\n"
        f"💎 Выводи подарки в Telegram\n\n"
        f"Нажми <b>Играть</b> чтобы начать! 👇",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )


async def send_stars_invoice(message: Message, stars: int):
    """Отправить инвойс на оплату Stars"""
    ton_amount = stars * STARS_TO_TON_RATE
    
    await bot.send_invoice(
        chat_id=message.chat.id,
        title=f"Пополнение {stars} ⭐",
        description=f"Пополнение баланса на {ton_amount:.2f} TON",
        payload=f"stars_{stars}_{message.from_user.id}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=f"{stars} Stars", amount=stars)],
        provider_token=""  # Для Stars provider_token пустой
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    """Подтверждение платежа"""
    await query.answer(ok=True)


@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: Message):
    """Обработка успешной оплаты"""
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    try:
        # Парсим payload: stars_AMOUNT_USERID
        parts = payload.split("_")
        stars = int(parts[1])
        user_id = int(parts[2])
        ton_amount = stars * STARS_TO_TON_RATE
        
        # Зачисляем TON на баланс
        new_balance = await update_balance(user_id, ton_amount)
        
        # Обрабатываем реферальный бонус
        bonus = await process_referral_bonus(user_id, ton_amount)
        
        # Записываем в историю
        try:
            supabase.table("star_payments").insert({
                "user_id": user_id,
                "stars": stars,
                "ton_amount": ton_amount,
                "payment_id": payment.telegram_payment_charge_id
            }).execute()
        except:
            pass
        
        await message.answer(
            f"✅ <b>Оплата успешна!</b>\n\n"
            f"💫 Оплачено: {stars} ⭐\n"
            f"💎 Зачислено: <b>+{ton_amount:.2f} TON</b>\n"
            f"💰 Баланс: <b>{new_balance:.2f} TON</b>",
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Payment: user={user_id}, stars={stars}, ton={ton_amount}")
        
    except Exception as e:
        logger.error(f"Payment processing error: {e}")
        await message.answer("❌ Ошибка обработки платежа. Обратитесь в поддержку.")


# ===== Проверка выводов =====
async def check_withdrawals():
    """Проверка новых заявок на вывод"""
    while True:
        try:
            result = supabase.table("withdrawals").select("*").eq("status", "pending").execute()
            
            for withdrawal in result.data:
                user_id = withdrawal.get("user_id")
                username = withdrawal.get("username", "unknown")
                gift_name = withdrawal.get("gift_name")
                gift_price = withdrawal.get("gift_price")
                
                # Уведомляем админа
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"📤 <b>Заявка на вывод</b>\n\n"
                        f"👤 @{username} (ID: {user_id})\n"
                        f"🎁 {gift_name}\n"
                        f"💰 {gift_price} TON",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Notify admin error: {e}")
                
                # Обновляем статус
                supabase.table("withdrawals").update({"status": "notified"}).eq("id", withdrawal["id"]).execute()
                
        except Exception as e:
            logger.error(f"Check withdrawals error: {e}")
        
        await asyncio.sleep(10)


# ===== Админ команды =====
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Статистика для админа"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        users = supabase.table("users").select("id, balance").execute()
        total_users = len(users.data)
        total_balance = sum(u.get("balance", 0) or 0 for u in users.data)
        
        withdrawals = supabase.table("withdrawals").select("id").eq("status", "pending").execute()
        pending = len(withdrawals.data)
        
        await message.answer(
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: {total_users}\n"
            f"💰 Общий баланс: {total_balance:.2f} TON\n"
            f"📤 Заявок на вывод: {pending}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@router.message(Command("give"))
async def cmd_give(message: Message):
    """Выдать TON пользователю"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Использование: /give USER_ID AMOUNT")
            return
        
        user_id = int(parts[1])
        amount = float(parts[2])
        
        new_balance = await update_balance(user_id, amount)
        await message.answer(f"✅ Выдано {amount} TON пользователю {user_id}\nНовый баланс: {new_balance}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@router.message(Command("take"))
async def cmd_take(message: Message):
    """Снять TON у пользователя"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Использование: /take USER_ID AMOUNT")
            return
        
        user_id = int(parts[1])
        amount = float(parts[2])
        
        new_balance = await update_balance(user_id, -amount)
        await message.answer(f"✅ Снято {amount} TON у пользователя {user_id}\nНовый баланс: {new_balance}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


async def main():
    logger.info("Starting GiftPepe Bot...")
    
    # Запускаем проверку выводов в фоне
    asyncio.create_task(check_withdrawals())
    
    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
