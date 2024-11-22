from flask import Flask, render_template, request, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FileField, SelectField
from wtforms.validators import DataRequired, Email, Length, ValidationError
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///guild.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Загрузка конфигурации из .env
from dotenv import load_dotenv
load_dotenv()

# Telegram конфигурация
app.config['TELEGRAM_TOKEN'] = os.getenv('TELEGRAM_TOKEN')
app.config['TELEGRAM_CHAT_ID'] = os.getenv('TELEGRAM_CHAT_ID')

logger.info(f"Loaded Telegram configuration: chat_id={app.config['TELEGRAM_CHAT_ID']}")

# Создаем папку для загрузки скриншотов, если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    timezone = db.Column(db.String(100), nullable=False)
    game_id = db.Column(db.String(100), nullable=False)
    telegram = db.Column(db.String(100))
    screenshot_path = db.Column(db.String(200), nullable=False)
    playtime = db.Column(db.String(100), nullable=False)
    game_nickname = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Application {self.name}>'

class ApplicationForm(FlaskForm):
    name = StringField('Имя', validators=[DataRequired(), Length(min=2, max=50)])
    age = StringField('Возраст', validators=[DataRequired()])
    timezone = StringField('Часовой пояс (можно город)', validators=[DataRequired()])
    game_id = StringField('Номер ID в игре', validators=[DataRequired()])
    game_time = StringField('Сколько времени проводите в игре', validators=[DataRequired()])
    screenshots = FileField('Скриншот профиля')
    additional_info = TextAreaField('Дополнительная информация')
    
    def validate_age(form, field):
        try:
            age = int(field.data)
            if age < 18:
                raise ValidationError('Для вступления в гильдию необходим возраст не менее 18 лет')
        except ValueError:
            raise ValidationError('Пожалуйста, введите корректный возраст')

with app.app_context():
    db.create_all()

async def send_to_telegram(application_data, screenshot_paths=None):
    """Send application data to Telegram channel"""
    logger.info("Начинаем отправку в Telegram...")
    
    if not app.config['TELEGRAM_TOKEN']:
        logger.error("Telegram token не настроен!")
        return False
        
    if not app.config['TELEGRAM_CHAT_ID']:
        logger.error("Telegram chat ID не настроен!")
        return False
    
    try:
        logger.info("Инициализация бота...")
        bot = Bot(token=app.config['TELEGRAM_TOKEN'])
        
        try:
            # Проверяем права бота
            bot_info = await bot.get_me()
            logger.info(f"Бот успешно подключен: {bot_info.username}")
            
            # Проверяем доступ к чату
            try:
                chat = await bot.get_chat(app.config['TELEGRAM_CHAT_ID'])
                logger.info(f"Успешно получен доступ к чату: {chat.title}")
            except Exception as e:
                logger.error(f"Ошибка доступа к чату: {str(e)}")
                return False
            
            # Format message
            try:
                message = (
                    "🎮 Новая заявка в гильдию!\n\n"
                    f"👤 Имя: {application_data['name']}\n"
                    f"🎂 Возраст: {application_data['age']}\n"
                    f"🌍 Часовой пояс: {application_data['timezone']}\n"
                    f"🎯 ID в игре: {application_data['game_id']}\n"
                    f"⏰ Время в игре: {application_data['game_time']}"
                )
                
                if application_data.get('additional_info'):
                    message += f"\n📝 Доп. информация: {application_data['additional_info']}"
            except Exception as e:
                logger.error(f"Ошибка форматирования сообщения: {str(e)}")
                return False
            
            # Send text message first
            try:
                await bot.send_message(
                    chat_id=app.config['TELEGRAM_CHAT_ID'],
                    text=message
                )
                logger.info("Текстовое сообщение отправлено успешно")
            except Exception as e:
                logger.error(f"Ошибка при отправке текстового сообщения: {str(e)}")
                return False

            # Send screenshots if any
            if screenshot_paths:
                for path in screenshot_paths:
                    try:
                        with open(path, 'rb') as photo:
                            await bot.send_photo(
                                chat_id=app.config['TELEGRAM_CHAT_ID'],
                                photo=photo,
                                caption=f"📸 Скриншот от {application_data['name']}"
                            )
                        logger.info(f"Скриншот отправлен успешно: {path}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке скриншота {path}: {str(e)}")
                        continue
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при работе с ботом: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {str(e)}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    form = ApplicationForm()
    if form.validate_on_submit():
        try:
            logger.info("Начало обработки новой заявки...")
            
            # Handle file upload first
            screenshots = []
            screenshot_paths = []
            if form.screenshots.data:
                try:
                    files = request.files.getlist('screenshots')
                    for file in files:
                        if file and allowed_file(file.filename):
                            # Ensure upload directory exists
                            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                            
                            # Generate a unique filename
                            ext = os.path.splitext(file.filename)[1]
                            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
                            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                            
                            # Save file
                            file.save(filepath)
                            screenshots.append(filename)
                            screenshot_paths.append(filepath)
                            logger.info(f"Сохранен скриншот: {filepath}")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении файла: {str(e)}")
                    flash('Произошла ошибка при загрузке скриншота. Пожалуйста, попробуйте еще раз.', 'error')
                    return render_template('apply.html', form=form)

            # Prepare application data
            application_data = {
                'name': form.name.data,
                'age': form.age.data,
                'timezone': form.timezone.data,
                'game_id': form.game_id.data,
                'game_time': form.game_time.data,
                'additional_info': form.additional_info.data,
                'screenshots': screenshots,
                'submitted_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Save to JSON file
            applications_file = os.path.join(app.config['UPLOAD_FOLDER'], 'applications.json')
            try:
                try:
                    with open(applications_file, 'r', encoding='utf-8') as f:
                        applications = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    applications = []

                applications.append(application_data)

                with open(applications_file, 'w', encoding='utf-8') as f:
                    json.dump(applications, f, indent=4, ensure_ascii=False)
                    
                logger.info("Заявка сохранена в JSON файл")
            except Exception as e:
                logger.error(f"Ошибка при сохранении заявки в JSON: {str(e)}")
                flash('Произошла ошибка при сохранении заявки. Пожалуйста, попробуйте еще раз.', 'error')
                return render_template('apply.html', form=form)

            # Send to Telegram
            try:
                success = asyncio.run(send_to_telegram(application_data, screenshot_paths))
                
                if success:
                    flash('Ваша заявка успешно отправлена! Мы свяжемся с вами в ближайшее время.', 'success')
                    logger.info("Заявка успешно обработана и отправлена")
                    return redirect(url_for('index'))
                else:
                    logger.error("Не удалось отправить заявку в Telegram")
                    flash('Заявка сохранена, но возникли проблемы с отправкой уведомления.', 'warning')
                    return redirect(url_for('index'))
            except Exception as e:
                logger.error(f"Ошибка при отправке в Telegram: {str(e)}")
                flash('Заявка сохранена, но возникли проблемы с отправкой уведомления.', 'warning')
                return redirect(url_for('index'))

        except Exception as e:
            logger.error(f"Общая ошибка при обработке заявки: {str(e)}")
            flash('Произошла ошибка при отправке заявки. Пожалуйста, попробуйте еще раз.', 'error')
            return render_template('apply.html', form=form)

    return render_template('apply.html', form=form)

@app.route('/admin')
def admin():
    applications = Application.query.order_by(Application.created_at.desc()).all()
    return render_template('admin.html', applications=applications)

@app.route('/admin/application/<int:id>', methods=['POST'])
def update_application(id):
    action = request.form.get('action')
    application = Application.query.get_or_404(id)
    
    if action == 'approve':
        application.status = 'approved'
        flash(f'Заявка от {application.name} одобрена', 'success')
    elif action == 'reject':
        application.status = 'rejected'
        flash(f'Заявка от {application.name} отклонена', 'success')
    
    db.session.commit()
    return redirect(url_for('admin'))

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == '__main__':
    app.run(debug=True)
