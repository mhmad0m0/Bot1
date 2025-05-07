from datetime import datetime
from src.extensions import db # Changed import from src.main to src.extensions

class Mod(db.Model):
    __tablename__ = 'mods'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    download_link = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    uploader_telegram_id = db.Column(db.BigInteger, nullable=False)
    status = db.Column(db.Text, nullable=False, default='pending_approval') # pending_approval, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    view_count = db.Column(db.Integer, default=0)
    download_count = db.Column(db.Integer, default=0)

    category = db.relationship('Category', backref=db.backref('mods', lazy=True))

    def __repr__(self):
        return f'<Mod {self.name}>'

