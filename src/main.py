import os
import sys
from datetime import datetime
from flask import Flask

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.extensions import db # Import db from extensions

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_very_secret_random_key_for_minecraft_mods_website')

# Database Configuration: Use DATABASE_URL from environment if available (for Render/PostgreSQL),
# otherwise, fall back to local SQLite.
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres"): # Render provides postgresql://
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(project_root, 'minecraft_mods_website.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Custom Jinja filter for datetime formatting
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            # If it's not ISO format, try to parse it if it's already a common string format
            # This part might need adjustment based on how dates are stored/retrieved
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f') # Example format
            except ValueError:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S') # Example format without microseconds
                except ValueError:
                     return value # Return as is if parsing fails
    if isinstance(value, datetime):
        return value.strftime(format)
    return value

app.jinja_env.filters['datetimeformat'] = datetimeformat

# Import models here after db is initialized and app is configured
# These imports are necessary for db.create_all() to know about the models
from src.models.mod import Mod
from src.models.category import Category
from src.models.admin import Admin

# Import blueprints
from src.routes.main_routes import main_routes
app.register_blueprint(main_routes)

# Ensure static/uploads/mods_images directory exists (for local dev, Render handles uploads differently)
static_uploads_mods_images_folder = os.path.join(app.static_folder, 'uploads', 'mods_images')
if not os.path.exists(static_uploads_mods_images_folder):
    os.makedirs(static_uploads_mods_images_folder, exist_ok=True)

# Placeholder image creation (for local dev)
static_images_folder = os.path.join(app.static_folder, 'images')
if not os.path.exists(static_images_folder):
    os.makedirs(static_images_folder, exist_ok=True)
placeholder_image_path = os.path.join(static_images_folder, 'placeholder.png')
if not os.path.exists(placeholder_image_path):
    try:
        # Create a tiny, valid PNG placeholder if possible, or just an empty file
        # For simplicity, creating an empty file. A real placeholder image should be added to the project.
        with open(placeholder_image_path, 'w') as f:
            f.write('') 
        print(f"Created placeholder file: {placeholder_image_path}. Please replace with an actual image or ensure it's in your repo.")
    except Exception as e:
        print(f"Could not create placeholder image: {e}")

# Create database tables and initial admin if they don't exist.
# This will run when the app starts. For Render, this might run during build/deploy.
# For production, migrations (e.g. Flask-Migrate) are a better approach for schema changes.
with app.app_context():
    try:
        db.create_all()
        print("Database tables checked/created.")
        owner_telegram_id = 7839645457 # This could also be an env var
        owner = Admin.query.filter_by(telegram_id=owner_telegram_id).first()
        if not owner:
            new_owner = Admin(telegram_id=owner_telegram_id, role='owner', username='SiteOwnerRender')
            db.session.add(new_owner)
            db.session.commit()
            print(f"Admin user with ID {owner_telegram_id} created.")
        else:
            print(f"Admin user with ID {owner_telegram_id} already exists.")
    except Exception as e:
        print(f"Error during initial database setup: {e}")
        print("This might be due to the database not being ready during build on Render.")
        print("Database setup will be attempted again when the app is fully running.")

if __name__ == '__main__':
    print("Starting Flask development server...")
    print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print("To run the Telegram bot, execute: python src/bot.py")
    # Set debug=False for production, but True is fine for local dev.
    # Render will use Gunicorn, not this app.run().
    app.run(host='0.0.0.0', port=5000, debug=True)

