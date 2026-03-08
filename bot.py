import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, Message,
    WebAppInfo
)
from aiogram.utils.deep_linking import decode_payload, create_start_link
from supabase import create_client, Client
import os

# ============== НАСТРОЙКИ ==============
BOT_TOKEN = "7948801307:AAEVkGlfE4kd0dmgifPZPdQb4FK3vvXrdUc"
SUPABASE_URL = "https://soxzsdwtutwdzygezsnk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNveHpzZHd0dXR3ZHp5Z2V6c25rIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjg2NzMwNywiZXhwIjoyMDg4NDQzMzA3fQ.VvVJW7abALCE0vPXU1gebKEf1JJhk8-Owk0b-VYK6jQ"
WEBAPP_URL = "https://giftpepe.github.io"
ADMIN_ID = 8339935446

# Курс: 1 Star = 0.02 TON (50 Stars = 1 TON)
STAR_TO_TON_RATE = 0.02
REFERRAL_PERCENT = 10  # 10% от пополнения

# ============== ИНИЦИАЛИЗАЦИЯ ==============
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==============

async def get_or_create_user(user: types.User, referrer_id: int = None) -> dict:
    """Получить или создать пользователя в БД"""
    try:
        # Проверяем существует ли пользователь
        result = supabase.table("users").select("*").eq("id", user.id).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        
        # Создаём нового пользователя
        new_user = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "photo_url": None,
            "balance": 0,
            "referrer_id": referrer_id,
            "referral_earnings": 0,
            "referral_count": 0
        }
        
        result = supabase.table("users").insert(new_user).execute()
        
        # Если есть реферер - увеличиваем его счётчик рефералов и уведомляем
        if referrer_id:
            # Обновляем счётчик рефералов
            supabase.table("users").update({
                "referral_count": supabase.table("users").select("referral_count").eq("id", referrer_id).execute().data[0].get("referral_count", 0) + 1
            }).eq("id", referrer_id).execute()
            
            # Уведомляем реферера
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 <b>Новый реферал!</b>\n\n"
                    f"Пользователь <b>{user.first_name}</b> (@{user.username or 'нет username'}) "
                    f"присоединился по вашей ссылке!\n\n"
                    f"💰 Вы будете получать <b>10%</b> от его пополнений!",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить реферера {referrer_id}: {e}")
        
        return result.data[0] if result.data else new_user
        
    except Exception as e:
        logger.error(f"Ошибка при создании пользователя: {e}")
        return None

async def update_balance(user_id: int, amount: float, description: str = "") -> bool:
    """Обновить баланс пользователя"""
    try:
        # Получаем текущий баланс
        result = supabase.table("users").select("balance").eq("id", user_id).execute()
        if not result.data:
            return False
        
        current_balance = float(result.data[0].get("balance", 0))
        new_balance = current_balance + amount
        
        # Обновляем баланс
        supabase.table("users").update({"balance": new_balance}).eq("id", user_id).execute()
        
        # Логируем транзакцию
        supabase.table("transactions").insert({
            "user_id": user_id,
            "type": "deposit" if amount > 0 else "withdraw",
            "amount": abs(amount),
            "description": description
        }).execute()
        
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления баланса: {e}")
        return False

async def process_referral_bonus(user_id: int, amount: float) -> None:
    """Начислить реферальный бонус"""
    try:
        # Получаем реферера
        result = supabase.table("users").select("referrer_id").eq("id", user_id).execute()
        if not result.data or not result.data[0].get("referrer_id"):
            return
        
        referrer_id = result.data[0]["referrer_id"]
        bonus = amount * (REFERRAL_PERCENT / 100)
        
        # Получаем данные реферера
        referrer_data = supabase.table("users").select("balance, referral_earnings").eq("id", referrer_id).execute()
        if not referrer_data.data:
            return
        
        current_balance = float(referrer_data.data[0].get("balance", 0))
        current_earnings = float(referrer_data.data[0].get("referral_earnings", 0))
        
        # Обновляем баланс и заработок с рефералов
        supabase.table("users").update({
            "balance": current_balance + bonus,
            "referral_earnings": current_earnings + bonus
        }).eq("id", referrer_id).execute()
        
        # Логируем транзакцию
        supabase.table("transactions").insert({
            "user_id": referrer_id,
            "type": "referral_bonus",
            "amount": bonus,
            "description": f"Реферальный бонус 10% от пополнения пользователя {user_id}"
        }).execute()
        
        # Получаем данные пользователя который пополнил
        user_data = supabase.table("users").select("first_name, username").eq("id", user_id).execute()
        user_name = "Пользователь"
        if user_data.data:
            user_name = user_data.data[0].get("first_name", "Пользователь")
        
        # Уведомляем реферера
        try:
            await bot.send_message(
                referrer_id,
                f"💰 <b>Реферальный бонус!</b>\n\n"
                f"Ваш реферал <b>{user_name}</b> пополнил баланс!\n"
                f"Вы получили <b>+{bonus:.2f} TON</b> (10%)\n\n"
                f"💎 Всего заработано с рефералов: <b>{current_earnings + bonus:.2f} TON</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить реферера о бонусе: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка начисления реферального бонуса: {e}")

# ============== КЛАВИАТУРЫ ==============

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎮 Играть",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )],
        [InlineKeyboardButton(text="💎 Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance")]
    ])

def get_deposit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура пополнения"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ 50 Stars (1 TON)", callback_data="pay_50"),
            InlineKeyboardButton(text="⭐ 100 Stars (2 TON)", callback_data="pay_100")
        ],
        [
            InlineKeyboardButton(text="⭐ 250 Stars (5 TON)", callback_data="pay_250"),
            InlineKeyboardButton(text="⭐ 500 Stars (10 TON)", callback_data="pay_500")
        ],
        [
            InlineKeyboardButton(text="⭐ 1000 Stars (20 TON)", callback_data="pay_1000"),
            InlineKeyboardButton(text="⭐ 2500 Stars (50 TON)", callback_data="pay_2500")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

# ============== ХЕНДЛЕРЫ ==============

@dp.message(CommandStart(deep_link=True))
async def start_with_referral(message: Message):
    """Старт с реферальной ссылкой"""
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    referrer_id = None
    
    if args and args.startswith("ref_"):
        try:
            referrer_id = int(args.replace("ref_", ""))
            # Нельзя быть своим рефералом
            if referrer_id == message.from_user.id:
                referrer_id = None
        except:
            referrer_id = None
    
    user = await get_or_create_user(message.from_user, referrer_id)
    
    welcome_text = (
        f"🎁 <b>Добро пожаловать в GiftPepe!</b>\n\n"
        f"Привет, <b>{message.from_user.first_name}</b>! 👋\n\n"
        f"🎰 Открывай кейсы с NFT-подарками\n"
        f"🔄 Апгрейди подарки для увеличения ценности\n"
        f"💰 Выводи или продавай свои NFT\n"
        f"👥 Приглашай друзей и получай 10% от их пополнений!\n\n"
    )
    
    if referrer_id:
        welcome_text += f"🎉 Вы присоединились по реферальной ссылке!\n\n"
    
    welcome_text += "⬇️ Нажмите <b>Играть</b> чтобы начать!"
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@dp.message(CommandStart())
async def start(message: Message):
    """Обычный старт без реферала"""
    user = await get_or_create_user(message.from_user)
    
    welcome_text = (
        f"🎁 <b>Добро пожаловать в GiftPepe!</b>\n\n"
        f"Привет, <b>{message.from_user.first_name}</b>! 👋\n\n"
        f"🎰 Открывай кейсы с NFT-подарками\n"
        f"🔄 Апгрейди подарки для увеличения ценности\n"
        f"💰 Выводи или продавай свои NFT\n"
        f"👥 Приглашай друзей и получай 10% от их пополнений!\n\n"
        f"⬇️ Нажмите <b>Играть</b> чтобы начать!"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.edit_text(
        f"🎁 <b>GiftPepe</b>\n\n"
        f"Привет, <b>{callback.from_user.first_name}</b>! 👋\n\n"
        f"🎰 Открывай кейсы с NFT-подарками\n"
        f"🔄 Апгрейди подарки для увеличения ценности\n"
        f"💰 Выводи или продавай свои NFT\n"
        f"👥 Приглашай друзей и получай 10% от их пополнений!\n\n"
        f"⬇️ Нажмите <b>Играть</b> чтобы начать!",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "balance")
async def show_balance(callback: types.CallbackQuery):
    """Показать баланс"""
    try:
        result = supabase.table("users").select("balance").eq("id", callback.from_user.id).execute()
        balance = float(result.data[0].get("balance", 0)) if result.data else 0
        
        await callback.message.edit_text(
            f"💰 <b>Ваш баланс</b>\n\n"
            f"💎 <b>{balance:.2f} TON</b>\n\n"
            f"Пополните баланс чтобы открывать кейсы!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Пополнить", callback_data="deposit")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка получения баланса: {e}")
        await callback.answer("Ошибка загрузки баланса", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "referrals")
async def show_referrals(callback: types.CallbackQuery):
    """Показать реферальную статистику"""
    try:
        result = supabase.table("users").select("referral_count, referral_earnings").eq("id", callback.from_user.id).execute()
        
        ref_count = 0
        ref_earnings = 0
        
        if result.data:
            ref_count = int(result.data[0].get("referral_count", 0))
            ref_earnings = float(result.data[0].get("referral_earnings", 0))
        
        ref_link = f"https://t.me/GiftPepeRobot?start=ref_{callback.from_user.id}"
        
        await callback.message.edit_text(
            f"👥 <b>Реферальная система</b>\n\n"
            f"Приглашайте друзей и получайте <b>10%</b> от каждого их пополнения!\n\n"
            f"📊 <b>Ваша статистика:</b>\n"
            f"├ 👤 Приглашено: <b>{ref_count}</b>\n"
            f"└ 💰 Заработано: <b>{ref_earnings:.2f} TON</b>\n\n"
            f"🔗 <b>Ваша ссылка:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            f"<i>Нажмите на ссылку чтобы скопировать</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=f"Присоединяйся к GiftPepe! 🎁 {ref_link}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка получения рефералов: {e}")
        await callback.answer("Ошибка загрузки данных", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "deposit")
async def show_deposit(callback: types.CallbackQuery):
    """Показать меню пополнения"""
    await callback.message.edit_text(
        f"💎 <b>Пополнение баланса</b>\n\n"
        f"Выберите сумму пополнения:\n\n"
        f"⭐ <b>50 Stars</b> = 1 TON\n"
        f"⭐ <b>100 Stars</b> = 2 TON\n"
        f"⭐ <b>250 Stars</b> = 5 TON\n"
        f"⭐ <b>500 Stars</b> = 10 TON\n"
        f"⭐ <b>1000 Stars</b> = 20 TON\n"
        f"⭐ <b>2500 Stars</b> = 50 TON\n\n"
        f"<i>Оплата через Telegram Stars ⭐</i>",
        reply_markup=get_deposit_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: types.CallbackQuery):
    """Создать инвойс для оплаты"""
    stars_amount = int(callback.data.replace("pay_", ""))
    ton_amount = stars_amount * STAR_TO_TON_RATE
    
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Пополнение {ton_amount:.0f} TON",
            description=f"Пополнение баланса GiftPepe на {ton_amount:.0f} TON",
            payload=f"deposit_{stars_amount}_{callback.from_user.id}",
            currency="XTR",  # Telegram Stars
            prices=[LabeledPrice(label=f"{ton_amount:.0f} TON", amount=stars_amount)],
            start_parameter=f"deposit_{stars_amount}"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка создания инвойса: {e}")
        await callback.answer("Ошибка создания платежа", show_alert=True)

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Подтверждение платежа"""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    """Успешный платёж"""
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    try:
        # Парсим payload: deposit_STARS_USERID
        parts = payload.split("_")
        stars_amount = int(parts[1])
        ton_amount = stars_amount * STAR_TO_TON_RATE
        
        # Начисляем баланс
        success = await update_balance(
            message.from_user.id, 
            ton_amount, 
            f"Пополнение через Stars: {stars_amount} Stars = {ton_amount} TON"
        )
        
        if success:
            # Начисляем реферальный бонус
            await process_referral_bonus(message.from_user.id, ton_amount)
            
            # Получаем новый баланс
            result = supabase.table("users").select("balance").eq("id", message.from_user.id).execute()
            new_balance = float(result.data[0].get("balance", 0)) if result.data else ton_amount
            
            await message.answer(
                f"✅ <b>Платёж успешен!</b>\n\n"
                f"💎 Зачислено: <b>+{ton_amount:.0f} TON</b>\n"
                f"💰 Ваш баланс: <b>{new_balance:.2f} TON</b>\n\n"
                f"Нажмите <b>Играть</b> чтобы открыть кейсы! 🎁",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "⚠️ Платёж получен, но возникла ошибка зачисления.\n"
                "Обратитесь в поддержку: @Star77787",
                reply_markup=get_main_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка обработки платежа: {e}")
        await message.answer(
            "⚠️ Ошибка обработки платежа.\n"
            "Обратитесь в поддержку: @Star77787",
            reply_markup=get_main_keyboard()
        )

# ============== АДМИН КОМАНДЫ ==============

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    """Админ панель"""
    if message.from_user.id != ADMIN_ID:
        return
    
    # Статистика
    try:
        users_count = len(supabase.table("users").select("id").execute().data)
        total_balance = sum(float(u.get("balance", 0)) for u in supabase.table("users").select("balance").execute().data)
        
        await message.answer(
            f"👑 <b>Админ панель</b>\n\n"
            f"📊 Статистика:\n"
            f"├ 👥 Пользователей: <b>{users_count}</b>\n"
            f"└ 💰 Общий баланс: <b>{total_balance:.2f} TON</b>\n\n"
            f"Команды:\n"
            f"/give ID AMOUNT - выдать TON\n"
            f"/take ID AMOUNT - забрать TON",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("give"))
async def give_balance(message: Message):
    """Выдать баланс пользователю"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Использование: /give USER_ID AMOUNT")
            return
        
        user_id = int(parts[1])
        amount = float(parts[2])
        
        success = await update_balance(user_id, amount, f"Выдано админом: {amount} TON")
        
        if success:
            await message.answer(f"✅ Выдано {amount} TON пользователю {user_id}")
        else:
            await message.answer("❌ Ошибка выдачи")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("take"))
async def take_balance(message: Message):
    """Забрать баланс у пользователя"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Использование: /take USER_ID AMOUNT")
            return
        
        user_id = int(parts[1])
        amount = float(parts[2])
        
        success = await update_balance(user_id, -amount, f"Снято админом: {amount} TON")
        
        if success:
            await message.answer(f"✅ Снято {amount} TON у пользователя {user_id}")
        else:
            await message.answer("❌ Ошибка снятия")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# ============== ЗАПУСК ==============

async def main():
    logger.info("🚀 Бот запускается...")
    
    # Удаляем вебхук если был
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
