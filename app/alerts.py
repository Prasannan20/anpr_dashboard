import os
import requests
from datetime import datetime, timezone
from flask import current_app
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _resolve_timezone():
    """Return timezone configured for notifications."""
    default_tz = os.getenv("TIMEZONE", "Asia/Kolkata")
    try:
        app = current_app._get_current_object()
        tz_name = app.config.get("TIMEZONE", default_tz)
    except RuntimeError:
        tz_name = default_tz
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo or timezone.utc


def _format_event_datetime(event):
    """Return localized date/time strings for the event."""
    ts = event.time_stamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    local_ts = ts.astimezone(_resolve_timezone())
    date_str = local_ts.strftime('%Y-%m-%d')
    offset = local_ts.strftime('%z') or '+0000'
    offset_fmt = f"{offset[:3]}:{offset[3:]}"
    time_str = f"{local_ts.strftime('%H:%M:%S %Z')} (UTC{offset_fmt})"
    return date_str, time_str

def send_telegram(event):
    """
    Sends a Telegram alert with full vehicle information and snapshot photo.
    """
    try:
        token = os.getenv("TG_BOT_TOKEN")
        chat_id = os.getenv("TG_CHAT_ID")

        if not token or not chat_id:
            print("[WARN] Telegram credentials missing in .env")
            return False

        event_date, event_time = _format_event_datetime(event)
        # Prepare message text (caption for photo)
        msg = (
            f"🚨 Vehicle ALERT 🚨\n"
            f"Plate: {event.vehicle_number}\n"
            f"Authorized As: {event.authorized_as}\n"
            f"Vehicle Type: {getattr(event, 'vehicle_type', 'Unknown')}\n"
            f"Status: {event.status}\n"
            f"Confidence: {event.confidence}%\n"
            f"Date: {event_date}\n"
            f"Time: {event_time}"
        )

        # Get snapshot file path
        snapshot_path = None
        if event.snapshot_path:
            try:
                # snapshot_path is relative like "static/snapshots/vehicle_xxx.jpg"
                # Get the Flask app instance to access root path
                try:
                    app = current_app._get_current_object()
                    # app.root_path points to the app directory (anpr_dashboard/app)
                    # snapshot_path is relative to app root (static/snapshots/...)
                    snapshot_path = os.path.join(app.root_path, event.snapshot_path)
                except (RuntimeError, AttributeError):
                    # Fallback: construct path manually if not in app context
                    # alerts.py is in app/, snapshot_path is relative to app/
                    base_dir = os.path.dirname(os.path.abspath(__file__))  # anpr_dashboard/app
                    snapshot_path = os.path.join(base_dir, event.snapshot_path)
                
                # Normalize path separators
                snapshot_path = os.path.normpath(snapshot_path)
                
                # Check if file exists
                if not os.path.exists(snapshot_path):
                    print(f"[WARN] Snapshot file not found: {snapshot_path}")
                    snapshot_path = None
            except Exception as e:
                print(f"[WARN] Error getting snapshot path: {e}")
                snapshot_path = None

        # Send message with photo if available, otherwise send text only
        if snapshot_path and os.path.exists(snapshot_path):
            # Send photo with caption
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            try:
                with open(snapshot_path, 'rb') as photo:
                    files = {'photo': photo}
                    data = {
                        'chat_id': chat_id,
                        'caption': msg,
                        'parse_mode': 'HTML'
                    }
                    response = requests.post(url, files=files, data=data, timeout=15)
            except Exception as e:
                print(f"[ERROR] Error reading snapshot file: {e}")
                # Fallback to text-only message
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = {"chat_id": chat_id, "text": msg}
                response = requests.post(url, data=data, timeout=10)
        else:
            # Send text-only message if no snapshot
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": msg}
            response = requests.post(url, data=data, timeout=10)

        if response.status_code == 200:
            print(f"[INFO] Telegram alert sent for {event.vehicle_number}" + (" (with photo)" if snapshot_path else " (text only)"))
            return True
        else:
            print(f"[ERROR] Telegram API failed: {response.text}")
            return False

    except Exception as e:
        print(f"[ERROR] Telegram alert exception: {e}")
        return False
