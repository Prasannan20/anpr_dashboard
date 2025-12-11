from datetime import datetime
from .extensions import db
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), default="viewer")
    @property
    def is_authenticated(self): return True
    @property
    def is_active(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

class Whitelist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    authorized_as = db.Column(db.String(20), nullable=False)

class VehicleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(db.String(20), index=True, nullable=False)
    time_stamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.String(3), nullable=False)  # IN | OUT
    authorized_as = db.Column(db.String(20), nullable=False)  # Principal/Faculty/Staff/Van/Unauthorized
    is_authorized = db.Column(db.Boolean, default=False, index=True)
    confidence = db.Column(db.Integer, default=0)
    alert_sent = db.Column(db.Boolean, default=False)
    snapshot_path = db.Column(db.String(255))
    vehicle_type = db.Column(db.String(20), default='Vehicle')
