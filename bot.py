import os
import logging
from io import BytesIO
from typing import List, Dict
import asyncio
from datetime import datetime

# Telegram bot imports
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Image processing imports
from PIL import Image, ImageEnhance, ImageFilter
from fpdf import FPDF

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8346818812:AAEhBj-Uvf3RgvoJzrW7zbqFQ0manE1kSvs"  # Замените на ваш токен
MAX_PHOTOS = 50  # Максимальное количество фото в одном PDF
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

class PDFConverter:
    def __init__(self):
        self.user_photos: Dict[int, List[bytes]] = {}
        
    def add_photo(self, user_id: int, photo_data: bytes) -> int:
        """Добавляет фото пользователя в очередь"""
        if user_id not in self.user_photos:
            self.user_photos[user_id] = []
        
        self.user_photos[user_id].append(photo_data)
        return len(self.user_photos[user_id])
    
    def clear_photos(self, user_id: int):
        """Очищает фото пользователя"""
        if user_id in self.user_photos:
            del self.user_photos[user_id]
    
    def get_photo_count(self, user_id: int) -> int:
        """Возвращает количество фото пользователя"""
        return len(self.user_photos.get(user_id, []))
    
    def enhance_image(self, image: Image.Image, enhancement_type: str = None) -> Image.Image:
        """Улучшает качество изображения"""
        try:
            if enhancement_type == "sharpen":
                return image.filter(ImageFilter.SHARPEN)
            elif enhancement_type == "brightness":
                enhancer = ImageEnhance.Brightness(image)
                return enhancer.enhance(1.2)
            elif enhancement_type == "contrast":
                enhancer = ImageEnhance.Contrast(image)
                return enhancer.enhance(1.1)
            return image
        except Exception as e:
            logger.error(f"Ошибка улучшения изображения: {e}")
            return image
    
    def create_pdf(self, user_id: int, page_format: str = "A4", 
                  orientation: str = "portrait", quality: str = "high",
                  enhancement: str = None) -> bytes:
        """Создает PDF из фотографий пользователя"""
        if user_id not in self.user_photos or not self.user_photos[user_id]:
            raise ValueError("Нет фотографий для конвертации")
        
        # Настройки PDF
        if orientation == "landscape":
            pdf = FPDF("L", "mm", page_format)
        else:
            pdf = FPDF("P", "mm", page_format)
        
        # Получаем размеры страницы
        if page_format == "A4":
            page_width, page_height = (297, 210) if orientation == "landscape" else (210, 297)
        elif page_format == "A3":
            page_width, page_height = (420, 297) if orientation == "landscape" else (297, 420)
        else:  # Letter
            page_width, page_height = (279, 216) if orientation == "landscape" else (216, 279)
        
        margin = 10
        img_width = page_width - 2 * margin
        img_height = page_height - 2 * margin
        
        for i, photo_data in enumerate(self.user_photos[user_id]):
            try:
                # Открываем изображение
                image = Image.open(BytesIO(photo_data))
                
                # Применяем улучшения
                if enhancement:
                    image = self.enhance_image(image, enhancement)
                
                # Конвертируем в RGB если нужно
                if image.mode != "RGB":
                    image = image.convert("RGB")
                
                # Масштабируем изображение с сохранением пропорций
                img_ratio = image.width / image.height
                target_ratio = img_width / img_height
                
                if img_ratio > target_ratio:
                    # Изображение шире - масштабируем по ширине
                    new_width = img_width
                    new_height = img_width / img_ratio
                else:
                    # Изображение выше - масштабируем по высоте
                    new_height = img_height
                    new_width = img_height * img_ratio
                
                # Изменяем размер с учетом DPI
                dpi_factor = 3.779  # 300 DPI / 72 DPI
                image = image.resize(
                    (int(new_width * dpi_factor), int(new_height * dpi_factor)), 
                    Image.Resampling.LANCZOS if quality == "high" else Image.Resampling.BILINEAR
                )
                
                # Сохраняем в временный буфер
                img_buffer = BytesIO()
                image.save(img_buffer, format="JPEG", 
                          quality=95 if quality == "high" else 75,
                          optimize=True)
                img_buffer.seek(0)
                
                # Добавляем страницу в PDF
                pdf.add_page()
                
                # Центрируем изображение
                x = (page_width - new_width) / 2
                y = (page_height - new_height) / 2
                
                pdf.image(img_buffer, x, y, new_width, new_height)
                
            except Exception as e:
                logger.error(f"Ошибка обработки изображения {i}: {e}")
                continue
        
        # Возвращаем PDF как bytes
        return bytes(pdf.output())

# Создаем экземпляр конвертера
converter = PDFConverter()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
🔥 **PDF CONVERTER BOT** 🔥

Мощный бот для конвертации фотографий в PDF!

📸 **Возможности:**
• Множественные фото в один PDF
• Различные форматы страниц (A4, A3, Letter)
• Портретная и альбомная ориентация
• Улучшение качества изображений
• Настройка качества PDF

🚀 **Как использовать:**
1. Отправьте фотографии (до 50 штук)
2. Нажмите "Создать PDF" когда закончите
3. Выберите настройки
4. Получите готовый PDF файл!

📝 Отправьте фото или используйте /help для подробной справки
"""
    
    keyboard = [
        [InlineKeyboardButton("📚 Справка", callback_data="help"),
         InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📖 **ПОДРОБНАЯ СПРАВКА**

🔸 **Основные команды:**
/start - Запуск бота
/help - Справка
/clear - Очистить текущие фото
/status - Показать количество загруженных фото

🔸 **Поддерживаемые форматы:**
• JPEG, JPG, PNG, WEBP
• Максимальный размер файла: 20MB
• Максимальное количество фото: 50

🔸 **Настройки PDF:**
📄 Форматы: A4, A3, Letter
🔄 Ориентация: Портретная, Альбомная
⚡ Качество: Высокое, Стандартное
✨ Улучшения: Резкость, Яркость, Контраст

🔸 **Процесс работы:**
1. Отправьте одну или несколько фотографий
2. Каждая фото добавляется в очередь
3. Нажмите "Создать PDF" для конвертации
4. Выберите желаемые настройки
5. Получите готовый PDF файл

💡 **Совет:** Отправляйте фото в том порядке, в котором хотите видеть их в PDF!
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)

async def clear_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка фотографий пользователя"""
    user_id = update.effective_user.id
    converter.clear_photos(user_id)
    
    await update.message.reply_text(
        "🗑️ Все фотографии очищены! Можете загружать новые.",
        reply_markup=get_main_keyboard()
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус загруженных фото"""
    user_id = update.effective_user.id
    count = converter.get_photo_count(user_id)
    
    status_text = f"""
📊 **ТЕКУЩИЙ СТАТУС**

📸 Загружено фотографий: **{count}**
📝 Максимум: {MAX_PHOTOS}
💾 Максимальный размер: {MAX_FILE_SIZE // (1024*1024)}MB

{"🟢 Готов к конвертации!" if count > 0 else "🔴 Загрузите фотографии"}
"""
    
    await update.message.reply_text(status_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

def get_main_keyboard():
    """Основная клавиатура"""
    keyboard = [
        [InlineKeyboardButton("🔄 Создать PDF", callback_data="create_pdf")],
        [InlineKeyboardButton("📊 Статус", callback_data="status"),
         InlineKeyboardButton("🗑️ Очистить", callback_data="clear")],
        [InlineKeyboardButton("📚 Справка", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения фотографий"""
    user_id = update.effective_user.id
    
    # Проверяем лимит фотографий
    current_count = converter.get_photo_count(user_id)
    if current_count >= MAX_PHOTOS:
        await update.message.reply_text(
            f"❌ Достигнут максимальный лимит фотографий ({MAX_PHOTOS})!\n"
            f"Создайте PDF или очистите текущие фото."
        )
        return
    
    try:
        # Получаем фото в лучшем качестве
        photo = update.message.photo[-1]
        
        # Проверяем размер файла
        if photo.file_size and photo.file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f"❌ Файл слишком большой! Максимальный размер: {MAX_FILE_SIZE // (1024*1024)}MB"
            )
            return
        
        # Скачиваем фото
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        
        # Добавляем фото в конвертер
        count = converter.add_photo(user_id, bytes(photo_bytes))
        
        # Отправляем подтверждение
        message_text = f"""
✅ **Фотография добавлена!**

📸 Всего фото: **{count}** / {MAX_PHOTOS}
📏 Размер: {len(photo_bytes) / 1024:.1f} KB

{"🟢 Можете добавить еще фото или создать PDF!" if count < MAX_PHOTOS else "🔴 Лимит достигнут! Создайте PDF."}
"""
        
        await update.message.reply_text(
            message_text, 
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке фотографии. Попробуйте еще раз."
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback запросов"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == "help":
        await help_command(update, context)
    
    elif data == "back_to_start":
        await start(update, context)
    
    elif data == "status":
        count = converter.get_photo_count(user_id)
        status_text = f"""
📊 **СТАТУС ЗАГРУЗКИ**

📸 Фотографий: **{count}** / {MAX_PHOTOS}
{"🟢 Готов к созданию PDF!" if count > 0 else "🔴 Загрузите фотографии"}
"""
        await query.edit_message_text(status_text, parse_mode='Markdown', reply_markup=get_main_keyboard())
    
    elif data == "clear":
        converter.clear_photos(user_id)
        await query.edit_message_text(
            "🗑️ Все фотографии очищены!", 
            reply_markup=get_main_keyboard()
        )
    
    elif data == "create_pdf":
        count = converter.get_photo_count(user_id)
        if count == 0:
            await query.edit_message_text(
                "❌ Нет фотографий для конвертации!\nЗагрузите фотографии и попробуйте снова.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Показываем меню настроек
        keyboard = [
            [InlineKeyboardButton("📄 A4", callback_data="format_A4"),
             InlineKeyboardButton("📄 A3", callback_data="format_A3"),
             InlineKeyboardButton("📄 Letter", callback_data="format_Letter")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚙️ **НАСТРОЙКИ PDF**\n\n📸 Фотографий: {count}\n\n📄 Выберите формат страницы:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif data.startswith("format_"):
        format_type = data.split("_")[1]
        context.user_data['format'] = format_type
        
        keyboard = [
            [InlineKeyboardButton("📱 Портретная", callback_data="orient_portrait"),
             InlineKeyboardButton("🖥️ Альбомная", callback_data="orient_landscape")],
            [InlineKeyboardButton("🔙 Назад", callback_data="create_pdf")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔄 **ОРИЕНТАЦИЯ** ({format_type})\n\nВыберите ориентацию страниц:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif data.startswith("orient_"):
        orientation = data.split("_")[1]
        context.user_data['orientation'] = orientation
        
        keyboard = [
            [InlineKeyboardButton("⚡ Высокое", callback_data="quality_high"),
             InlineKeyboardButton("📊 Стандартное", callback_data="quality_standard")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"format_{context.user_data.get('format', 'A4')}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✨ **КАЧЕСТВО**\n\nФормат: {context.user_data.get('format', 'A4')}\n"
            f"Ориентация: {'Портретная' if orientation == 'portrait' else 'Альбомная'}\n\n"
            f"Выберите качество PDF:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif data.startswith("quality_"):
        quality = data.split("_")[1]
        context.user_data['quality'] = quality
        
        keyboard = [
            [InlineKeyboardButton("🌟 Без улучшений", callback_data="enhance_none"),
             InlineKeyboardButton("🔪 Резкость", callback_data="enhance_sharpen")],
            [InlineKeyboardButton("☀️ Яркость", callback_data="enhance_brightness"),
             InlineKeyboardButton("🎭 Контраст", callback_data="enhance_contrast")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"orient_{context.user_data.get('orientation', 'portrait')}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🎨 **УЛУЧШЕНИЯ**\n\n"
            f"Формат: {context.user_data.get('format', 'A4')}\n"
            f"Ориентация: {'Портретная' if context.user_data.get('orientation') == 'portrait' else 'Альбомная'}\n"
            f"Качество: {'Высокое' if quality == 'high' else 'Стандартное'}\n\n"
            f"Выберите тип улучшения изображений:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif data.startswith("enhance_"):
        enhancement = data.split("_")[1] if data != "enhance_none" else None
        
        # Запускаем создание PDF
        await query.edit_message_text("🔄 **Создаю PDF...** Пожалуйста, подождите...")
        
        try:
            pdf_data = converter.create_pdf(
                user_id=user_id,
                page_format=context.user_data.get('format', 'A4'),
                orientation=context.user_data.get('orientation', 'portrait'),
                quality=context.user_data.get('quality', 'high'),
                enhancement=enhancement
            )
            
            # Генерируем имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"photos_to_pdf_{timestamp}.pdf"
            
            # Отправляем PDF файл
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=BytesIO(pdf_data),
                filename=filename,
                caption=f"""
✅ **PDF создан успешно!**

📸 Фотографий обработано: {converter.get_photo_count(user_id)}
📄 Формат: {context.user_data.get('format', 'A4')}
🔄 Ориентация: {'Портретная' if context.user_data.get('orientation') == 'portrait' else 'Альбомная'}
⚡ Качество: {'Высокое' if context.user_data.get('quality') == 'high' else 'Стандартное'}
🎨 Улучшение: {enhancement or 'Нет'}
💾 Размер файла: {len(pdf_data) / 1024:.1f} KB

🚀 Готов к новой конвертации!
""",
                parse_mode='Markdown'
            )
            
            # Очищаем фотографии пользователя
            converter.clear_photos(user_id)
            
            # Удаляем сообщение с прогрессом
            await query.delete_message()
            
        except Exception as e:
            logger.error(f"Ошибка создания PDF: {e}")
            await query.edit_message_text(
                f"❌ Произошла ошибка при создании PDF!\n\nОшибка: {str(e)}",
                reply_markup=get_main_keyboard()
            )
    
    elif data == "back_to_main":
        count = converter.get_photo_count(user_id)
        await query.edit_message_text(
            f"🏠 **ГЛАВНОЕ МЕНЮ**\n\n📸 Загружено фотографий: {count}",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для документов (если кто-то отправит не фото)"""
    await update.message.reply_text(
        "❌ Поддерживаются только изображения!\n"
        "📸 Отправьте фотографии в формате JPEG, PNG или WEBP."
    )

def main():
    """Запуск бота"""
    print("🚀 Запуск PDF Converter Bot...")
    
    # Проверяем наличие токена
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Ошибка: Установите токен бота в переменной BOT_TOKEN!")
        print("💡 Получите токен у @BotFather в Telegram")
        print("🔧 Откройте файл bot.py и замените 'YOUR_BOT_TOKEN_HERE' на ваш токен")
        return
    
    try:
        # Создаем приложение с новым синтаксисом
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("clear", clear_photos))
        app.add_handler(CommandHandler("status", status))
        
        # Обработчики сообщений
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        
        # Обработчик callback запросов
        app.add_handler(CallbackQueryHandler(handle_callback))
        
        print("✅ Бот успешно запущен! Готов к работе...")
        print("📱 Найдите вашего бота в Telegram и отправьте /start")
        print("🛑 Для остановки нажмите Ctrl+C")
        
        # Запускаем бота с polling
        app.run_polling(drop_pending_updates=True)
        
    except telegram.error.InvalidToken:
        print("❌ ОШИБКА: Неверный токен бота!")
        print("🔧 Проверьте правильность токена от @BotFather")
        
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        print("\n🔧 Попробуйте следующее:")
        print("1. Обновите библиотеку: pip install --upgrade python-telegram-bot")
        print("2. Переустановите зависимости: pip install python-telegram-bot pillow fpdf2")
        print("3. Проверьте подключение к интернету")

if __name__ == '__main__':
    main()