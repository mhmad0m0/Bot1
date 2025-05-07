from datetime import datetime
from src.extensions import db # Changed import from src.main to src.extensions

class Admin(db.Model):
    __tablename__ = 'admins'

    telegram_id = db.Column(db.BigInteger, primary_key=True, unique=True)
    username = db.Column(db.Text, nullable=True)
    role = db.Column(db.Text, nullable=False, default='owner') # e.g., owner
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Admin {self.telegram_id} ({self.role})>'

