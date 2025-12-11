from .extensions import db, socketio
from .models import VehicleEvent
from .alerts import send_telegram

def compute_is_authorized(authorized_as: str) -> bool:
    return authorized_as in ('Principal', 'Faculty', 'Staff', 'Van')

def make_event_dict(e: VehicleEvent):
    return {
        'id': e.id,
        'vehicle_number': e.vehicle_number,
        'time_stamp': e.time_stamp.isoformat(),
        'status': e.status,
        'authorized_as': e.authorized_as,
        'is_authorized': e.is_authorized,
        'confidence': e.confidence,
        'alert_sent': e.alert_sent,
        'snapshot_path': e.snapshot_path or '',
        'vehicle_type': getattr(e, 'vehicle_type', 'Vehicle')
    }

def emit_vehicle_event(data):
    auth_as = data.get('authorized_as', 'Unauthorized')
    is_auth = compute_is_authorized(auth_as)
    e = VehicleEvent(
        vehicle_number=data['vehicle_number'],
        status=data.get('status', 'IN'),
        authorized_as=auth_as,
        is_authorized=is_auth,
        confidence=int(data.get('confidence', 0)),
        snapshot_path=data.get('snapshot_path', ''),
        vehicle_type=data.get('vehicle_type', 'Vehicle')
    )
    db.session.add(e)
    db.session.commit()
    if not e.is_authorized:
        if send_telegram(e):
            e.alert_sent = True
            db.session.commit()
    socketio.emit('vehicle_event', make_event_dict(e), namespace='/ws/live')
    return e
