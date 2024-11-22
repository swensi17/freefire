import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from flask import Flask, request, redirect, url_for, flash, render_template
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FileField, SelectField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.utils import secure_filename
import json
from datetime import datetime

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'BELYI94')

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(NAME, AGE, TIMEZONE, GAME_ID, TELEGRAM_USERNAME, 
 SCREENSHOT, PLAYTIME, GAME_NICKNAME, RULES_ACCEPT) = range(9)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = 'your_secret_key_here'

class ApplicationForm(FlaskForm):
    username = StringField('Discord Username', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    role = SelectField('Desired Role', choices=[
        ('dps', 'DPS'),
        ('tank', 'Tank'),
        ('healer', 'Healer'),
        ('support', 'Support')
    ], validators=[DataRequired()])
    experience = TextAreaField('Gaming Experience', validators=[DataRequired(), Length(min=100, max=2000)])
    availability = TextAreaField('Weekly Availability', validators=[DataRequired()])
    screenshots = FileField('Screenshots')
    additional_info = TextAreaField('Additional Information')

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    form = ApplicationForm()
    if form.validate_on_submit():
        try:
            # Create uploads directory if it doesn't exist
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            
            # Handle file upload
            screenshots = []
            if form.screenshots.data:
                files = request.files.getlist('screenshots')
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        screenshots.append(filename)

            # Save application data (you can modify this to save to a database)
            application_data = {
                'username': form.username.data,
                'email': form.email.data,
                'role': form.role.data,
                'experience': form.experience.data,
                'availability': form.availability.data,
                'additional_info': form.additional_info.data,
                'screenshots': screenshots,
                'submitted_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # For now, we'll save to a JSON file (you can modify this to use a database)
            applications_file = os.path.join(app.config['UPLOAD_FOLDER'], 'applications.json')
            try:
                with open(applications_file, 'r') as f:
                    applications = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                applications = []

            applications.append(application_data)

            with open(applications_file, 'w') as f:
                json.dump(applications, f, indent=4, ensure_ascii=False)

            flash('Ваша заявка успешно отправлена! Мы свяжемся с вами в ближайшее время.', 'success')
            return redirect(url_for('index'))

        except Exception as e:
            app.logger.error(f"Error submitting application: {str(e)}")
            flash('Произошла ошибка при отправке заявки. Пожалуйста, попробуйте еще раз.', 'error')

    return render_template('apply.html', form=form)

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/submit_application', methods=['POST'])
def submit_application():
    try:
        name = request.form.get('name')
        age = request.form.get('age')
        experience = request.form.get('experience')
        about = request.form.get('about')
        telegram = request.form.get('telegram')
        
        # Handle file upload
        screenshot = request.files.get('screenshot')
        if screenshot:
            # Ensure the filename is secure
            filename = secure_filename(screenshot.filename)
            # Save the file
            screenshot.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # Here you can add code to save the application to a database
        # For now, we'll just flash a success message
        
        flash('Ваша заявка успешно отправлена! Мы свяжемся с вами в ближайшее время.', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash('Произошла ошибка при отправке заявки. Пожалуйста, попробуйте еще раз.', 'error')
        return redirect(url_for('index'))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the conversation and ask for name."""
    await update.message.reply_text(
        "👋 Добро пожаловать! Я помогу вам подать заявку в гильдию.\n"
        "Для начала, как вас зовут?"
    )
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store name and ask for age."""
    context.user_data['name'] = update.message.text
    await update.message.reply_text('Сколько вам лет?')
    return AGE

async def age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store age and ask for timezone."""
    try:
        age = int(update.message.text)
        if age < 13:
            await update.message.reply_text('Извините, но вы слишком молоды для вступления в гильдию.')
            return ConversationHandler.END
        context.user_data['age'] = age
        await update.message.reply_text('Укажите ваш часовой пояс или город:')
        return TIMEZONE
    except ValueError:
        await update.message.reply_text('Пожалуйста, введите возраст числом.')
        return AGE

async def timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store timezone and ask for game ID."""
    context.user_data['timezone'] = update.message.text
    await update.message.reply_text('Введите ваш ID в игре:')
    return GAME_ID

async def game_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store game ID and ask for Telegram username."""
    context.user_data['game_id'] = update.message.text
    await update.message.reply_text(
        'Введите ваш Telegram username (необязательно, но рекомендуется):\n'
        'Если не хотите указывать, отправьте "-"'
    )
    return TELEGRAM_USERNAME

async def telegram_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store Telegram username and ask for screenshot."""
    context.user_data['telegram_username'] = update.message.text
    await update.message.reply_text(
        'Пожалуйста, отправьте скриншот вашего игрового профиля:'
    )
    return SCREENSHOT

async def screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store screenshot and ask for playtime."""
    if not update.message.photo:
        await update.message.reply_text('Пожалуйста, отправьте изображение.')
        return SCREENSHOT
    
    context.user_data['screenshot_id'] = update.message.photo[-1].file_id
    await update.message.reply_text('Сколько времени в день вы проводите в игре?')
    return PLAYTIME

async def playtime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store playtime and ask for game nickname."""
    context.user_data['playtime'] = update.message.text
    await update.message.reply_text('Введите ваш ник в игре:')
    return GAME_NICKNAME

async def game_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store game nickname and ask for rules acceptance."""
    context.user_data['game_nickname'] = update.message.text
    keyboard = [['Да, принимаю'], ['Нет, не принимаю']]
    await update.message.reply_text(
        'Вы подтверждаете, что прочитали и согласны с правилами гильдии?',
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return RULES_ACCEPT

async def rules_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete the conversation and send application to admin."""
    if update.message.text == 'Нет, не принимаю':
        await update.message.reply_text(
            'Для вступления в гильдию необходимо принять правила. До свидания!',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Format application message
    application = (
        f"🆕 Новая заявка в гильдию!\n\n"
        f"👤 Имя: {context.user_data['name']}\n"
        f"📅 Возраст: {context.user_data['age']}\n"
        f"🌍 Часовой пояс: {context.user_data['timezone']}\n"
        f"🎮 ID в игре: {context.user_data['game_id']}\n"
        f"📱 Telegram: {context.user_data['telegram_username']}\n"
        f"⏰ Время в игре: {context.user_data['playtime']}\n"
        f"🎯 Игровой ник: {context.user_data['game_nickname']}"
    )

    # Send application to admin
    await context.bot.send_message(chat_id=f"@{ADMIN_USERNAME}", text=application)
    await context.bot.send_photo(
        chat_id=f"@{ADMIN_USERNAME}",
        photo=context.user_data['screenshot_id'],
        caption="Скриншот профиля"
    )

    await update.message.reply_text(
        '✅ Спасибо! Ваша заявка отправлена на рассмотрение.\n'
        'Администратор свяжется с вами в ближайшее время.',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    await update.message.reply_text(
        'Заполнение заявки отменено. До свидания!',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main():
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, timezone)],
            GAME_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, game_id)],
            TELEGRAM_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_username)],
            SCREENSHOT: [MessageHandler(filters.PHOTO, screenshot)],
            PLAYTIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, playtime)],
            GAME_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, game_nickname)],
            RULES_ACCEPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rules_accept)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
