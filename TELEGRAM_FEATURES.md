# Telegram Alert Features - Complete Guide

## 📱 Overview

The ANPR Dashboard includes an integrated Telegram alert system that automatically sends notifications when unauthorized vehicles are detected. This feature helps security personnel get instant alerts on their mobile devices or Telegram desktop app.

---

## 🚀 How It Works

### **Automatic Alert Triggering**

1. **Vehicle Detection**: When a vehicle is detected by the camera/video feed
2. **Authorization Check**: The system checks if the vehicle is authorized:
   - ✅ **Authorized**: Principal, Faculty, Staff, or Van → **No alert sent**
   - ❌ **Unauthorized**: Not in whitelist or marked as "Unauthorized" → **Alert sent**
3. **Telegram Notification**: If unauthorized, an alert is automatically sent to your Telegram chat
4. **Status Tracking**: The system marks `alert_sent = True` in the database

### **Alert Flow**

```
Vehicle Detected
    ↓
Check Whitelist
    ↓
Is Authorized? → NO → Send Telegram Alert → Mark alert_sent = True
    ↓
    YES → No Alert
```

---

## ⚙️ Configuration

### **Step 1: Create a Telegram Bot**

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. BotFather will give you a **Bot Token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
5. Save this token - you'll need it!

### **Step 2: Get Your Chat ID**

1. Search for your bot in Telegram (the one you just created)
2. Start a conversation with your bot
3. Send any message to your bot
4. Open this URL in your browser (replace `YOUR_BOT_TOKEN` with your actual token):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
5. Look for `"chat":{"id":123456789}` in the response
6. Copy the **chat ID** number

### **Step 3: Configure Environment Variables**

Create or edit a `.env` file in your project root with:

```env
TG_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TG_CHAT_ID=123456789
```

**Important**: 
- Replace with your actual bot token and chat ID
- Keep these values secret - don't commit them to version control
- The `.env` file should be in `.gitignore`

---

## 📨 Alert Message Format

When an unauthorized vehicle is detected, you'll receive a message like this:

```
🚨 Vehicle ALERT 🚨
Plate: KA 01 AB 1234
Authorized As: Unauthorized
Vehicle Type: Car
Status: IN
Confidence: 85%
Date: 2024-01-15
Time: 14:30:45 UTC
```

### **Message Details**

- **🚨 Alert Emoji**: Visual indicator for urgent alerts
- **Plate**: Detected license plate number
- **Authorized As**: Authorization status (usually "Unauthorized")
- **Vehicle Type**: Type of vehicle (Car, Motorcycle, Bus, Truck, Vehicle)
- **Status**: Entry/Exit status (IN or OUT)
- **Confidence**: Detection confidence percentage (0-100%)
- **Date**: Detection date (YYYY-MM-DD format)
- **Time**: Detection time (HH:MM:SS UTC format)

---

## 🔧 Technical Implementation

### **Files Involved**

1. **`app/alerts.py`**: Contains the `send_telegram()` function
2. **`app/events.py`**: Calls `send_telegram()` when unauthorized vehicles are detected
3. **`app/models.py`**: `VehicleEvent` model has `alert_sent` field to track status

### **Code Flow**

```python
# In app/events.py
def emit_vehicle_event(data):
    # ... create vehicle event ...
    if not e.is_authorized:  # Only for unauthorized vehicles
        if send_telegram(e):  # Send alert
            e.alert_sent = True  # Mark as sent
            db.session.commit()
```

### **Error Handling**

- ✅ **Success**: Returns `True`, logs success message
- ❌ **Missing Credentials**: Returns `False`, logs warning (doesn't crash)
- ❌ **API Error**: Returns `False`, logs error details
- ❌ **Network Error**: Catches exception, logs error, returns `False`

---

## 📊 Dashboard Integration

### **Alert Status Display**

In the dashboard, you can see which events triggered alerts:

- **⚠ Alert Sent**: Alert was successfully sent to Telegram
- **No**: No alert was sent (either authorized vehicle or alert failed)

### **Alert Tracking**

- Each `VehicleEvent` has an `alert_sent` boolean field
- This is visible in:
  - Dashboard table (Alert column)
  - CSV exports
  - PDF exports

---

## 🎯 Use Cases

### **1. Security Monitoring**
- Get instant notifications when unauthorized vehicles enter
- Monitor entry/exit in real-time
- Track suspicious vehicles

### **2. Access Control**
- Alerts for vehicles not in whitelist
- Notifications for restricted areas
- Compliance monitoring

### **3. Emergency Response**
- Quick alerts for security incidents
- Immediate notification to security personnel
- Mobile-first alert system

---

## 🔒 Security Features

### **Safe Configuration**
- Credentials stored in environment variables (not in code)
- `.env` file should be in `.gitignore`
- No hardcoded tokens or chat IDs

### **Error Resilience**
- System continues working even if Telegram is unavailable
- Graceful degradation (logs warning, doesn't crash)
- Alert status tracking for debugging

---

## 🛠️ Troubleshooting

### **Alert Not Sending?**

1. **Check Credentials**:
   ```bash
   # Verify .env file exists and has correct values
   cat .env | grep TG_
   ```

2. **Test Bot Token**:
   - Visit: `https://api.telegram.org/botYOUR_TOKEN/getMe`
   - Should return bot information

3. **Check Chat ID**:
   - Make sure you've sent at least one message to your bot
   - Verify chat ID is correct (should be a number)

4. **Check Logs**:
   - Look for `[WARN]` or `[ERROR]` messages in console
   - Check if credentials are being loaded

5. **Network Issues**:
   - Ensure server has internet access
   - Check firewall settings
   - Verify Telegram API is accessible

### **Common Issues**

| Issue | Solution |
|-------|----------|
| "Telegram credentials missing" | Add `TG_BOT_TOKEN` and `TG_CHAT_ID` to `.env` |
| "Telegram API failed" | Check bot token, verify bot is active |
| No alerts received | Verify chat ID, ensure you've messaged the bot |
| Alerts for authorized vehicles | This shouldn't happen - check authorization logic |

---

## 📈 Future Enhancements (Possible)

- **Photo Attachments**: Send vehicle snapshot with alert
- **Multiple Recipients**: Send to multiple chat IDs
- **Alert Groups**: Different alerts for different vehicle types
- **Alert Frequency**: Rate limiting to prevent spam
- **Custom Messages**: Configurable alert message templates
- **Alert History**: Track all sent alerts in database

---

## 📝 Example .env File

```env
# Telegram Bot Configuration
TG_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz1234567890
TG_CHAT_ID=123456789

# Other configuration
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///anpr.db
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
```

---

## ✅ Summary

**Telegram Features:**
- ✅ Automatic alerts for unauthorized vehicles
- ✅ Real-time notifications
- ✅ Full vehicle information in alerts
- ✅ Alert status tracking
- ✅ Configurable via environment variables
- ✅ Error handling and graceful degradation
- ✅ Mobile and desktop support

**When Alerts Are Sent:**
- Only for unauthorized vehicles
- Automatically triggered on detection
- Includes all relevant vehicle information
- Status tracked in database

**Setup Required:**
1. Create Telegram bot via @BotFather
2. Get bot token and chat ID
3. Add to `.env` file
4. Restart application

The system is ready to use once configured! 🚀








