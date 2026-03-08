import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice, PreCheckoutQuery
from aiogram.enums import ParseMode
from supabase import create_client

# Настройки
BOT_TOKEN = "7948801307:AAEVkGlfE4kd0dmgifPZPdQb4FK3vvXrdUc"
SUPABASE_URL = "https://soxzsdwtutwdzygezsnk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNveHpzZHd0dXR3ZHp5Z2V6c25rIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjg2NzMwNywiZXhwIjoyMDg4NDQzMzA3fQ.VvVJW7abALCE0vPXU1gebKEf1JJhk8-Owk0b-VYK6jQ"
ADMIN_ID = 8339935446
WEBAPP_URL = "https://giftpepe.github.io"

# Курс: 100 Stars = 1.1 TON
STARS_TO_TON = {
    100: 1.1,
    200: 2.2,
    500: 5.5,
    1000: 11.0,
    2500: 27.5,
    5000: 55.0
}

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Команда /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    # Проверяем реферальный параметр
    args = message.text.split()
    referrer_id = None
    
    if len(args) > 1:
        param = args[1]
        
        # Если это запрос на пополнение: pay_100, pay_200, etc
        if param.startswith("pay_"):
            try:
                stars = int(param.replace("pay_", ""))
                if stars in STARS_TO_TON:
                    await send_invoice(message, stars)
                    return
            except:
                pass
        
        # Если это реферальная ссылка: ref_123456
        elif param.startswith("ref_"):
            try:
                referrer_id = int(param.replace("ref_", ""))
                if referrer_id == user_id:
                    referrer_id = None
            except:
                pass
    
    # Проверяем существует ли пользователь
    result = supabase.table("users").select("*").eq("id", user_id).execute()
    
    if not result.data:
        # Создаём нового пользователя
        supabase.table("users").insert({
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "balance": 0,
            "referrer_id": referrer_id,
            "referral_count": 0,
            "referral_earnings": 0
        }).execute()
        
        # Уведомляем реферера
        if referrer_id:
            try:
                # Увеличиваем счётчик рефералов
                ref_data = supabase.table("users").select("referral_count").eq("id", referrer_id).execute()
                if ref_data.data:
                    new_count = (ref_data.data[0].get("referral_count") or 0) + 1
                    supabase.table("users").update({"referral_count": new_count}).eq("id", referrer_id).execute()
                
                await bot.send_message(
                    referrer_id,
                    f"🎉 По вашей ссылке присоединился новый игрок!\n"
                    f"👤 @{username or first_name}\n"
                    f"💰 Вы получите 10% от его пополнений!"
                )
            except Exception as e:
                logging.error(f"Ошибка уведомления реферера: {e}")
    
    # Кнопка играть
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    
    await message.answer(
        f"🎁 <b>Добро пожаловать в GiftPepe!</b>\n\n"
        f"🎰 Открывай кейсы с NFT подарками\n"
        f"⬆️ Апгрейди подарки для увеличения стоимости\n"
        f"💎 Выводи ценные NFT на свой кошелёк\n"
        f"👥 Приглашай друзей и получай 10% от их пополнений!\n\n"
        f"<i>Нажми кнопку ниже чтобы начать игру:</i>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

# Функция отправки инвойса
async def send_invoice(message: types.Message, stars: int):
    ton_amount = STARS_TO_TON.get(stars, 0)
    
    await message.answer_invoice(
        title=f"Пополнение {ton_amount} TON",
        description=f"Вы получите {ton_amount} TON на баланс в GiftPepe",
        payload=f"topup_{stars}_{message.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{stars} Stars", amount=stars)],
        provider_token=""
    )

# Pre-checkout
@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

# Успешная оплата
@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    try:
        parts = payload.split("_")
        stars = int(parts[1])
        user_id = int(parts[2])
    except:
        stars = 100
        user_id = message.from_user.id
    
    ton_amount = STARS_TO_TON.get(stars, 1.1)
    
    # Получаем данные пользователя
    result = supabase.table("users").select("*").eq("id", user_id).execute()
    
    if result.data:
        user = result.data[0]
        new_balance = (user.get("balance") or 0) + ton_amount
        referrer_id = user.get("referrer_id")
        
        # Обновляем баланс
        supabase.table("users").update({"balance": new_balance}).eq("id", user_id).execute()
        
        # Записываем платёж
        supabase.table("star_payments").insert({
            "user_id": user_id,
            "stars": stars,
            "ton_amount": ton_amount,
            "payment_id": payment.telegram_payment_charge_id
        }).execute()
        
        # Начисляем реферальный бонус 10%
        if referrer_id:
            bonus = ton_amount * 0.1
            ref_data = supabase.table("users").select("balance, referral_earnings").eq("id", referrer_id).execute()
            
            if ref_data.data:
                ref_user = ref_data.data[0]
                new_ref_balance = (ref_user.get("balance") or 0) + bonus
                new_ref_earnings = (ref_user.get("referral_earnings") or 0) + bonus
                
                supabase.table("users").update({
                    "balance": new_ref_balance,
                    "referral_earnings": new_ref_earnings
                }).eq("id", referrer_id).execute()
                
                # Уведомляем реферера
                try:
                    username = message.from_user.username or message.from_user.first_name
                    await bot.send_message(
                        referrer_id,
                        f"💰 Реферальный бонус!\n\n"
                        f"👤 @{username} пополнил баланс\n"
                        f"🎁 Ваш бонус: +{bonus:.2f} TON (10%)\n"
                        f"💎 Ваш баланс: {new_ref_balance:.2f} TON"
                    )
                except:
                    pass
    
    await message.answer(
        f"✅ Оплата прошла успешно!\n\n"
        f"💎 Зачислено: {ton_amount} TON\n"
        f"⭐ Оплачено: {stars} Stars\n\n"
        f"Возвращайтесь в игру!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
    )

# Проверка выводов
async def check_withdrawals():
    while True:
        try:
            result = supabase.table("withdrawals").select("*").eq("status", "pending").execute()
            
            for withdrawal in result.data:
                user_id = withdrawal.get("user_id")
                username = withdrawal.get("username") or str(user_id)
                gift_name = withdrawal.get("gift_name")
                gift_price = withdrawal.get("gift_price")
                
                # Уведомляем админа
                await bot.send_message(
                    ADMIN_ID,
                    f"📤 <b>Заявка на вывод!</b>\n\n"
                    f"👤 @{username} (ID: {user_id})\n"
                    f"🎁 {gift_name}\n"
                    f"💰 {gift_price} TON",
                    parse_mode=ParseMode.HTML
                )
                
                # Обновляем статус
                supabase.table("withdrawals").update({"status": "notified"}).eq("id", withdrawal["id"]).execute()
                
        except Exception as e:
            logging.error(f"Ошибка проверки выводов: {e}")
        
        await asyncio.sleep(10)

# Админ команды
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = supabase.table("users").select("*").execute()
    total_users = len(users.data)
    total_balance = sum(u.get("balance", 0) for u in users.data)
    
    withdrawals = supabase.table("withdrawals").select("*").eq("status", "pending").execute()
    pending = len(withdrawals.data)
    
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Общий баланс: {total_balance:.2f} TON\n"
        f"📤 Заявок на вывод: {pending}",
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("give"))
async def cmd_give(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = float(parts[2])
        
        result = supabase.table("users").select("balance").eq("id", user_id).execute()
        if result.data:
            new_balance = (result.data[0].get("balance") or 0) + amount
            supabase.table("users").update({"balance": new_balance}).eq("id", user_id).execute()
            await message.answer(f"✅ Выдано {amount} TON пользователю {user_id}")
        else:
            await message.answer("❌ Пользователь не найден")
    except:
        await message.answer("❌ Использование: /give USER_ID AMOUNT")

@dp.message(Command("take"))
async def cmd_take(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = float(parts[2])
        
        result = supabase.table("users").select("balance").eq("id", user_id).execute()
        if result.data:
            new_balance = max(0, (result.data[0].get("balance") or 0) - amount)
            supabase.table("users").update({"balance": new_balance}).eq("id", user_id).execute()
            await message.answer(f"✅ Снято {amount} TON у пользователя {user_id}")
        else:
            await message.answer("❌ Пользователь не найден")
    except:
        await message.answer("❌ Использование: /take USER_ID AMOUNT")

# Запуск
async def main():
    logging.info("Бот запущен!")
    asyncio.create_task(check_withdrawals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
