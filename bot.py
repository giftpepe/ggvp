import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, 
    LabeledPrice, PreCheckoutQuery, CallbackQuery,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineQueryResultPhoto, ChosenInlineResult
)
from supabase import create_client, Client

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "7948801307:AAEVkGlfE4kd0dmgifPZPdQb4FK3vvXrdUc"
ADMIN_ID = 8339935446
SUPABASE_URL = "https://soxzsdwtutwdzygezsnk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNveHpzZHd0dXR3ZHp5Z2V6c25rIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjg2NzMwNywiZXhwIjoyMDg4NDQzMzA3fQ.VvVJW7abALCE0vPXU1gebKEf1JJhk8-Owk0b-VYK6jQ"
CHANNEL_ID = "@giftpepechannel"  # Канал для обязательной подписки

# Курс: 100 Stars = 1.1 TON
STARS_TO_TON_RATE = 1.1 / 100

# URL фото приветствия - теперь используется с Vercel
WELCOME_PHOTO_URL = "https://xenms.netlify.app/GiftPepe.jpg"

# URL WebApp - Vercel
WEBAPP_URL = "https://xenms.netlify.app/"

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ===== ПРОВЕРКА ПОДПИСКИ =====
async def check_subscription(user_id: int) -> bool:
    """Проверяет, подписан ли пользователь на канал"""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False


# ===== START =====
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    
    # Проверяем подписку на канал
    is_subscribed = await check_subscription(user.id)
    
    if not is_subscribed:
        # Показываем сообщение с требованием подписки
        caption = """👋 <b>Добро пожаловать в GiftPepe!</b>

🎁 Чтобы начать играть, подпишись на наш канал:
📢 <b>@giftpepechannel</b>

Там ты найдешь:
• Новости проекта
• Промокоды и бонусы
• Розыгрыши подарков"""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/giftpepechannel")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
        ])
        
        # Отправляем фото с подписью
        try:
            await message.answer_photo(
                photo=WELCOME_PHOTO_URL,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except:
            # Если фото не загрузилось — отправляем текст
            await message.answer(caption, reply_markup=keyboard, parse_mode="HTML")
        return
    
    # Если подписан — показываем приветствие
    await show_welcome(message, user, args)


# ===== ПРОВЕРКА ПОДПИСКИ (кнопка) =====
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    user = callback.from_user
    
    # Проверяем подписку
    is_subscribed = await check_subscription(user.id)
    
    if is_subscribed:
        # Подписан — показываем приветствие
        await callback.message.delete()
        await show_welcome(callback.message, user)
        await callback.answer("✅ Подписка подтверждена!")
    else:
        # Не подписан — показываем ошибку
        await callback.answer("❌ Ты еще не подписан на канал!", show_alert=True)


# ===== ПРИВЕТСТВИЕ =====
async def show_welcome(message_or_callback, user: types.User, args: str = None):
    """Показывает приветственное сообщение с кнопкой Играть"""
    
    # Создаём/обновляем пользователя
    try:
        supabase.table('users').upsert({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }, on_conflict='id').execute()
    except Exception as e:
        logger.error(f"User upsert error: {e}")
    
    # Обработка реферальной ссылки
    if args and args.startswith('ref_'):
        try:
            referrer_id = int(args.replace('ref_', ''))
            if referrer_id != user.id:
                # Проверяем что юзер новый
                result = supabase.table('users').select('referrer_id').eq('id', user.id).single().execute()
                if result.data and not result.data.get('referrer_id'):
                    # Записываем реферера
                    supabase.table('users').update({'referrer_id': referrer_id}).eq('id', user.id).execute()
                    # Увеличиваем счётчик рефералов
                    supabase.rpc('increment_referral_count', {'user_id': referrer_id}).execute()
                    # Уведомляем реферера
                    try:
                        await bot.send_message(referrer_id, f"🎉 По вашей ссылке присоединился @{user.username or user.first_name}!")
                    except:
                        pass
        except Exception as e:
            logger.error(f"Referral error: {e}")
    
    # Обработка оплаты через deep link
    if args and args.startswith('pay_'):
        try:
            stars = int(args.replace('pay_', ''))
            if stars >= 1:
                await send_invoice(message_or_callback.chat.id, user.id, stars)
                return
        except:
            pass
    
    # Приветственное сообщение
    caption = """🎁 <b>Добро пожаловать в GiftPepe!</b>

🎰 Открывай кейсы и выигрывай NFT-подарки
⬆️ Апгрейди подарки для увеличения стоимости
💎 Выводи на свой Telegram-аккаунт

Нажми кнопку ниже чтобы начать играть! 👇"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    
    # Отправляем фото с подписью
    try:
        await message_or_callback.answer_photo(
            photo=WELCOME_PHOTO_URL,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except:
        # Если фото не загрузилось — отправляем текст
        await message_or_callback.answer(caption, reply_markup=keyboard, parse_mode="HTML")


# ===== INLINE MODE =====
@dp.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    """Обработчик инлайн-запросов @GiftPepeRobot"""
    user = inline_query.from_user
    query = inline_query.query.lower().strip()
    
    # Проверяем подписку
    is_subscribed = await check_subscription(user.id)
    
    if not is_subscribed:
        # Если не подписан — показываем сообщение о подписке
        results = [
            InlineQueryResultArticle(
                id="not_subscribed",
                title="📢 Требуется подписка",
                description="Подпишись на @giftpepechannel чтобы играть",
                input_message_content=InputTextMessageContent(
                    message_text=f"👋 <b>Привет!</b>\n\n"
                                f"🎁 Чтобы начать играть в GiftPepe, подпишись на канал:\n"
                                f"📢 @giftpepechannel\n\n"
                                f"Затем напиши боту /start",
                    parse_mode="HTML"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться", url="https://t.me/giftpepechannel")],
                    [InlineKeyboardButton(text="🤖 Открыть бота", url="https://t.me/GiftPepeRobot")]
                ])
            )
        ]
        await inline_query.answer(results, cache_time=1)
        return
    
    # Если подписан — показываем кнопку игры
    # Проверяем запрос (Play или пустой)
    if query in ["", "play", "играть", "start", "начать"]:
        results = [
            InlineQueryResultPhoto(
                id="giftpepe_welcome",
                title="🎮 Играть в GiftPepe",
                description="Открывай кейсы и выигрывай NFT-подарки!",
                photo_url=WELCOME_PHOTO_URL,
                thumbnail_url=WELCOME_PHOTO_URL,
                caption="🎁 <b>GiftPepe — открывай кейсы и выигрывай NFT-подарки!</b>\n\n"
                        "🎰 Кейсы с редкими подарками\n"
                        "⬆️ Апгрейд предметов\n"
                        "💎 Вывод на Telegram-аккаунт\n\n"
                        "Нажми кнопку ниже чтобы начать! 👇",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=WEBAPP_URL))]
                ])
            )
        ]
        await inline_query.answer(results, cache_time=1)
    else:
        # Для других запросов — пустой ответ
        await inline_query.answer([], cache_time=1)


# ===== INLINE RESULT CHOSEN =====
@dp.chosen_inline_result()
async def chosen_inline_result_handler(chosen_result: ChosenInlineResult):
    """Логируем когда пользователь выбрал инлайн-результат"""
    logger.info(f"Inline result chosen by user {chosen_result.from_user.id}: {chosen_result.result_id}")


# ===== ОТПРАВКА ИНВОЙСА =====
async def send_invoice(chat_id: int, user_id: int, stars: int):
    ton_amount = stars * STARS_TO_TON_RATE
    
    prices = [LabeledPrice(label=f"Пополнение {stars} ⭐", amount=stars)]
    
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"Пополнение баланса",
        description=f"{stars} Stars = {ton_amount:.2f} TON на баланс в GiftPepe",
        payload=f"deposit_{user_id}_{stars}",
        currency="XTR",
        prices=prices
    )


# ===== PRE-CHECKOUT =====
@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# ===== УСПЕШНАЯ ОПЛАТА =====
@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    try:
        # Парсим payload: deposit_USER_ID_STARS
        parts = payload.split('_')
        if len(parts) >= 3 and parts[0] == 'deposit':
            user_id = int(parts[1])
            stars = int(parts[2])
            ton_amount = stars * STARS_TO_TON_RATE
            
            # Зачисляем на баланс
            result = supabase.table('users').select('balance, referrer_id').eq('id', user_id).single().execute()
            current_balance = result.data.get('balance', 0) if result.data else 0
            referrer_id = result.data.get('referrer_id') if result.data else None
            
            new_balance = current_balance + ton_amount
            supabase.table('users').update({'balance': new_balance}).eq('id', user_id).execute()
            
            # Логируем платёж
            supabase.table('star_payments').insert({
                'user_id': user_id,
                'stars': stars,
                'ton_amount': ton_amount,
                'payment_id': payment.telegram_payment_charge_id
            }).execute()
            
            # Реферальный бонус 10%
            if referrer_id:
                bonus = ton_amount * 0.1
                ref_result = supabase.table('users').select('balance, referral_earnings').eq('id', referrer_id).single().execute()
                if ref_result.data:
                    ref_balance = ref_result.data.get('balance', 0)
                    ref_earnings = ref_result.data.get('referral_earnings', 0)
                    supabase.table('users').update({
                        'balance': ref_balance + bonus,
                        'referral_earnings': ref_earnings + bonus
                    }).eq('id', referrer_id).execute()
                    
                    # Уведомляем реферера
                    try:
                        await bot.send_message(
                            referrer_id,
                            f"💰 Ваш реферал пополнил баланс!\n+{bonus:.2f} TON на ваш счёт (10% бонус)"
                        )
                    except:
                        pass
            
            await message.answer(
                f"✅ Успешно оплачено!\n\n"
                f"💰 +{ton_amount:.2f} TON зачислено на баланс\n"
                f"⭐ Оплачено: {stars} Stars\n\n"
                f"Вернитесь в приложение и обновите страницу.",
                parse_mode="HTML"
            )
            logger.info(f"Payment success: user={user_id}, stars={stars}, ton={ton_amount}")
            
    except Exception as e:
        logger.error(f"Payment processing error: {e}")
        await message.answer("❌ Ошибка обработки платежа. Обратитесь в поддержку.")


# ===== ПРОВЕРКА PENDING PAYMENTS =====
async def check_pending_payments():
    """Проверяет таблицу pending_payments и отправляет инвойсы"""
    while True:
        try:
            result = supabase.table('pending_payments').select('*').eq('status', 'pending').execute()
            
            if result.data:
                for payment in result.data:
                    user_id = payment['user_id']
                    stars = payment['stars']
                    payment_id = payment['id']
                    
                    try:
                        # Отправляем инвойс
                        await send_invoice(user_id, user_id, stars)
                        
                        # Помечаем как отправленный
                        supabase.table('pending_payments').update({'status': 'sent'}).eq('id', payment_id).execute()
                        logger.info(f"Invoice sent to user {user_id} for {stars} stars")
                        
                    except Exception as e:
                        logger.error(f"Failed to send invoice to {user_id}: {e}")
                        # Помечаем как ошибку
                        supabase.table('pending_payments').update({'status': 'error'}).eq('id', payment_id).execute()
                        
        except Exception as e:
            logger.error(f"Check pending payments error: {e}")
        
        await asyncio.sleep(5)


# ===== ПРОВЕРКА ВЫВОДОВ =====
async def check_withdrawals():
    """Проверяет таблицу withdrawals и уведомляет админа"""
    while True:
        try:
            result = supabase.table('withdrawals').select('*').eq('status', 'pending').execute()
            
            if result.data:
                for withdrawal in result.data:
                    withdraw_id = withdrawal['id']
                    user_id = withdrawal['user_id']
                    username = withdrawal.get('username', 'unknown')
                    gift_name = withdrawal['gift_name']
                    gift_price = withdrawal['gift_price']
                    
                    # Отправляем уведомление админу с кнопками
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{withdraw_id}_{user_id}"),
                            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{withdraw_id}_{user_id}")
                        ]
                    ])
                    
                    await bot.send_message(
                        ADMIN_ID,
                        f"📤 <b>Заявка на вывод #{withdraw_id}</b>\n\n"
                        f"👤 @{username} (ID: {user_id})\n"
                        f"🎁 {gift_name}\n"
                        f"💰 {gift_price} TON",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    
                    # Помечаем как notified
                    supabase.table('withdrawals').update({'status': 'notified'}).eq('id', withdraw_id).execute()
                    logger.info(f"Withdrawal notification sent: #{withdraw_id}")
                    
        except Exception as e:
            logger.error(f"Check withdrawals error: {e}")
        
        await asyncio.sleep(10)


# ===== ОБРАБОТКА КНОПОК ПОДТВЕРЖДЕНИЯ/ОТКЛОНЕНИЯ =====
@dp.callback_query(F.data.startswith('confirm_'))
async def confirm_withdrawal(callback: CallbackQuery):
    parts = callback.data.split('_')
    withdraw_id = int(parts[1])
    user_id = int(parts[2])
    
    try:
        # Получаем данные о выводе
        result = supabase.table('withdrawals').select('*').eq('id', withdraw_id).single().execute()
        if not result.data:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        withdrawal = result.data
        
        # Получаем username пользователя
        user_result = supabase.table('users').select('username').eq('id', user_id).single().execute()
        username = user_result.data.get('username', 'unknown') if user_result.data else 'unknown'
        
        # Обновляем статус
        supabase.table('withdrawals').update({'status': 'completed'}).eq('id', withdraw_id).execute()
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Подарок отправлен!</b>\n\n"
                f"🎁 {withdrawal['gift_name']}\n"
                f"💰 {withdrawal['gift_price']} TON\n\n"
                f"📬 Отправлен на ваш аккаунт @{username}",
                parse_mode="HTML"
            )
        except:
            pass
        
        await callback.message.edit_text(
            f"✅ Подтверждено!\n\n"
            f"@{username} получил {withdrawal['gift_name']} ({withdrawal['gift_price']} TON)"
        )
        await callback.answer("Подтверждено!")
        
    except Exception as e:
        logger.error(f"Confirm withdrawal error: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)


@dp.callback_query(F.data.startswith('reject_'))
async def reject_withdrawal(callback: CallbackQuery):
    parts = callback.data.split('_')
    withdraw_id = int(parts[1])
    user_id = int(parts[2])
    
    try:
        # Получаем данные о выводе
        result = supabase.table('withdrawals').select('*').eq('id', withdraw_id).single().execute()
        if not result.data:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        withdrawal = result.data
        
        # Возвращаем подарок в инвентарь
        supabase.table('inventory').insert({
            'user_id': user_id,
            'gift_name': withdrawal['gift_name'],
            'gift_image': withdrawal['gift_image'],
            'gift_price': withdrawal['gift_price']
        }).execute()
        
        # Обновляем статус
        supabase.table('withdrawals').update({'status': 'rejected'}).eq('id', withdraw_id).execute()
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"❌ <b>Подарок не удалось вывести</b>\n\n"
                f"🎁 {withdrawal['gift_name']}\n\n"
                f"Подарок возвращён в ваш инвентарь.",
                parse_mode="HTML"
            )
        except:
            pass
        
        await callback.message.edit_text(
            f"❌ Отклонено!\n\n"
            f"{withdrawal['gift_name']} возвращён пользователю"
        )
        await callback.answer("Отклонено!")
        
    except Exception as e:
        logger.error(f"Reject withdrawal error: {e}")
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# ===== MAIN =====
async def main():
    logger.info("🤖 Бот запускается...")
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_pending_payments())
    asyncio.create_task(check_withdrawals())
    
    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())