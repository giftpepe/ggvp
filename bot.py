import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice, PreCheckoutQuery, CallbackQuery
from aiogram.enums import ParseMode
from supabase import create_client

# Настройки
BOT_TOKEN = "7948801307:AAEVkGlfE4kd0dmgifPZPdQb4FK3vvXrdUc"
SUPABASE_URL = "https://soxzsdwtutwdzygezsnk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNveHpzZHd0dXR3ZHp5Z2V6c25rIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjg2NzMwNywiZXhwIjoyMDg4NDQzMzA3fQ.VvVJW7abALCE0vPXU1gebKEf1JJhk8-Owk0b-VYK6jQ"
WEBAPP_URL = "https://giftpepe.github.io"
ADMIN_ID = 8339935446

# Курс: 100 Stars = 1.1 TON
STARS_TO_TON_RATE = 1.1 / 100

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# /start - только описание и кнопка играть
@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    # Проверяем реферала
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    # Проверяем существует ли пользователь
    existing = supabase.table("users").select("id, referrer_id").eq("id", user_id).execute()
    
    if not existing.data:
        # Новый пользователь
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
            supabase.table("users").update({
                "referral_count": supabase.table("users").select("referral_count").eq("id", referrer_id).execute().data[0]["referral_count"] + 1
            }).eq("id", referrer_id).execute()
            
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 По вашей ссылке присоединился новый пользователь!\n"
                    f"👤 @{username or first_name}\n"
                    f"💰 Вы будете получать 10% от его пополнений!"
                )
            except:
                pass
    else:
        # Обновляем данные существующего
        supabase.table("users").update({
            "username": username,
            "first_name": first_name
        }).eq("id", user_id).execute()
    
    # Отправляем приветствие
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    
    await message.answer(
        "🎁 <b>Gift Pepe</b> — открывай кейсы, выбивай редкие NFT подарки!\n\n"
        "🎰 Крути кейсы и получай ценные призы\n"
        "⬆️ Апгрейди подарки для увеличения стоимости\n"
        "💎 Выводи NFT или продавай за TON\n\n"
        "Нажми <b>Играть</b> чтобы начать!",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )


# Обработка pre_checkout_query
@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# Обработка успешной оплаты
@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    payment = message.successful_payment
    user_id = message.from_user.id
    stars = payment.total_amount
    ton_amount = round(stars * STARS_TO_TON_RATE, 2)
    
    logging.info(f"Payment: user={user_id}, stars={stars}, ton={ton_amount}")
    
    # Получаем текущий баланс и реферера
    user_data = supabase.table("users").select("balance, referrer_id").eq("id", user_id).execute()
    
    if user_data.data:
        current_balance = float(user_data.data[0].get("balance", 0))
        referrer_id = user_data.data[0].get("referrer_id")
        
        # Обновляем баланс
        new_balance = current_balance + ton_amount
        supabase.table("users").update({"balance": new_balance}).eq("id", user_id).execute()
        
        # Записываем платёж
        supabase.table("star_payments").insert({
            "user_id": user_id,
            "stars": stars,
            "ton_amount": ton_amount,
            "payment_id": payment.telegram_payment_charge_id
        }).execute()
        
        # Реферальный бонус 10%
        if referrer_id:
            bonus = round(ton_amount * 0.1, 2)
            ref_data = supabase.table("users").select("balance, referral_earnings").eq("id", referrer_id).execute()
            if ref_data.data:
                ref_balance = float(ref_data.data[0].get("balance", 0))
                ref_earnings = float(ref_data.data[0].get("referral_earnings", 0))
                supabase.table("users").update({
                    "balance": ref_balance + bonus,
                    "referral_earnings": ref_earnings + bonus
                }).eq("id", referrer_id).execute()
                
                try:
                    username = message.from_user.username or message.from_user.first_name
                    await bot.send_message(
                        referrer_id,
                        f"💰 <b>Реферальный бонус!</b>\n\n"
                        f"👤 @{username} пополнил баланс\n"
                        f"🎁 Ваш бонус: <b>+{bonus} TON</b>",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
        
        await message.answer(
            f"✅ <b>Оплата прошла успешно!</b>\n\n"
            f"⭐ Оплачено: {stars} Stars\n"
            f"💎 Зачислено: <b>{ton_amount} TON</b>\n\n"
            f"Возвращайся в игру!",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer("❌ Ошибка: пользователь не найден")


# Callback для подтверждения/отклонения вывода
@dp.callback_query(F.data.startswith("withdraw_"))
async def process_withdraw_callback(callback: CallbackQuery):
    data = callback.data.split("_")
    action = data[1]  # approve или reject
    withdraw_id = int(data[2])
    
    # Получаем данные о выводе
    withdraw_data = supabase.table("withdrawals").select("*").eq("id", withdraw_id).execute()
    
    if not withdraw_data.data:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    
    withdraw = withdraw_data.data[0]
    user_id = withdraw["user_id"]
    gift_name = withdraw["gift_name"]
    gift_price = withdraw["gift_price"]
    gift_image = withdraw.get("gift_image", "")
    
    if action == "approve":
        # Подтверждаем вывод
        supabase.table("withdrawals").update({"status": "approved"}).eq("id", withdraw_id).execute()
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Подарок выведен!</b>\n\n"
                f"🎁 {gift_name}\n"
                f"💰 Стоимость: <b>{gift_price} TON</b>\n\n"
                f"Подарок отправлен на ваш кошелёк!",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Failed to notify user {user_id}: {e}")
        
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>ПОДТВЕРЖДЕНО</b>",
            parse_mode=ParseMode.HTML
        )
        await callback.answer("Вывод подтверждён!")
        
    elif action == "reject":
        # Отклоняем вывод
        supabase.table("withdrawals").update({"status": "rejected"}).eq("id", withdraw_id).execute()
        
        # Возвращаем подарок в инвентарь
        supabase.table("inventory").insert({
            "user_id": user_id,
            "gift_name": gift_name,
            "gift_image": gift_image,
            "gift_price": gift_price
        }).execute()
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"❌ <b>Не удалось вывести подарок</b>\n\n"
                f"🎁 {gift_name}\n"
                f"💰 Стоимость: <b>{gift_price} TON</b>\n\n"
                f"Подарок возвращён в ваш инвентарь.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Failed to notify user {user_id}: {e}")
        
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
            parse_mode=ParseMode.HTML
        )
        await callback.answer("Вывод отклонён, подарок возвращён!")


# Проверка новых запросов на пополнение
async def check_pending_payments():
    while True:
        try:
            pending = supabase.table("pending_payments").select("*").eq("status", "pending").execute()
            
            for payment in pending.data:
                user_id = payment["user_id"]
                stars = payment["stars"]
                payment_id = payment["id"]
                
                # Отправляем инвойс
                try:
                    await bot.send_invoice(
                        chat_id=user_id,
                        title="Пополнение баланса",
                        description=f"Пополнение на {round(stars * STARS_TO_TON_RATE, 2)} TON",
                        payload=f"topup_{user_id}_{stars}",
                        currency="XTR",
                        prices=[LabeledPrice(label="Stars", amount=stars)]
                    )
                    # Помечаем как отправленный
                    supabase.table("pending_payments").update({"status": "sent"}).eq("id", payment_id).execute()
                except Exception as e:
                    logging.error(f"Failed to send invoice to {user_id}: {e}")
                    supabase.table("pending_payments").update({"status": "error"}).eq("id", payment_id).execute()
        
        except Exception as e:
            logging.error(f"Error checking pending payments: {e}")
        
        await asyncio.sleep(3)


# Проверка новых заявок на вывод
async def check_withdrawals():
    while True:
        try:
            pending = supabase.table("withdrawals").select("*").eq("status", "pending").execute()
            
            for withdraw in pending.data:
                withdraw_id = withdraw["id"]
                user_id = withdraw["user_id"]
                username = withdraw.get("username", "Unknown")
                gift_name = withdraw["gift_name"]
                gift_price = withdraw["gift_price"]
                
                # Кнопки подтверждения/отклонения
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"withdraw_approve_{withdraw_id}"),
                        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"withdraw_reject_{withdraw_id}")
                    ]
                ])
                
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"📤 <b>Заявка на вывод #{withdraw_id}</b>\n\n"
                        f"👤 @{username}\n"
                        f"🆔 ID: <code>{user_id}</code>\n"
                        f"🎁 Подарок: <b>{gift_name}</b>\n"
                        f"💰 Стоимость: <b>{gift_price} TON</b>",
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                    # Помечаем как notified (ждём решения админа)
                    supabase.table("withdrawals").update({"status": "notified"}).eq("id", withdraw_id).execute()
                except Exception as e:
                    logging.error(f"Failed to notify admin about withdrawal: {e}")
        
        except Exception as e:
            logging.error(f"Error checking withdrawals: {e}")
        
        await asyncio.sleep(5)


# Админ команды
@dp.message(Command("admin"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = supabase.table("users").select("id, balance").execute()
    total_users = len(users.data)
    total_balance = sum(float(u.get("balance", 0)) for u in users.data)
    
    pending = supabase.table("withdrawals").select("id").eq("status", "notified").execute()
    pending_count = len(pending.data)
    
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Общий баланс: {total_balance:.2f} TON\n"
        f"📤 Ожидают вывода: {pending_count}",
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("give"))
async def give_balance(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /give USER_ID AMOUNT")
        return
    
    try:
        target_id = int(args[1])
        amount = float(args[2])
        
        user_data = supabase.table("users").select("balance").eq("id", target_id).execute()
        if user_data.data:
            current = float(user_data.data[0].get("balance", 0))
            supabase.table("users").update({"balance": current + amount}).eq("id", target_id).execute()
            await message.answer(f"✅ Выдано {amount} TON пользователю {target_id}")
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("take"))
async def take_balance(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /take USER_ID AMOUNT")
        return
    
    try:
        target_id = int(args[1])
        amount = float(args[2])
        
        user_data = supabase.table("users").select("balance").eq("id", target_id).execute()
        if user_data.data:
            current = float(user_data.data[0].get("balance", 0))
            new_balance = max(0, current - amount)
            supabase.table("users").update({"balance": new_balance}).eq("id", target_id).execute()
            await message.answer(f"✅ Снято {amount} TON у пользователя {target_id}")
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


async def main():
    logging.info("Bot starting...")
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_pending_payments())
    asyncio.create_task(check_withdrawals())
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
