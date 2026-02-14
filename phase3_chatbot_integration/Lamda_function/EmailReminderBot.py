import boto3
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from boto3.dynamodb.conditions import Attr
try: 
   from zoneinfo import ZoneInfo 
except ImportError: 
   from backports.zoneinfo import ZoneInfo # For older Python runtimes

# ======================================================
# CONFIG
# ======================================================

TABLE_NAME = "MedicationReminders"
# SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:381414049366:PillReminderBot"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

ses = boto3.client("ses")

# ======================================================
# MAIN HANDLER (EventBridge → UTC)
# ======================================================

def lambda_handler(event, context):
    logger.info("Lambda triggered")
    logger.info(event)

    # Current UTC time
    utc_now = datetime.now(timezone.utc)

    # Scan ACTIVE reminders only
    response = table.scan(
        FilterExpression=Attr("Status").eq("ACTIVE")
    )

    items = response.get("Items", [])
    logger.info(f"Found {len(items)} active reminders")

    for item in items:
        try:
            process_reminder(item, utc_now)
        except Exception as e:
            logger.error(
                f"Error processing reminder {item.get('ReminderId')}: {str(e)}"
            )

    return {
        "status": "completed",
        "checked": len(items)
    }

# ======================================================
# PROCESS EACH REMINDER
# ======================================================

def process_reminder(item, utc_now):
    email = item["UserEmail"]
    med_name = item["MedicationName"]
    reminder_times = item.get("ReminderTimes", [])
    timezone_name = item["Timezone"]

    # Convert UTC → USER TIMEZONE
    user_tz = ZoneInfo(timezone_name)
    user_now = utc_now.astimezone(user_tz)

    current_time_str = user_now.strftime("%H:%M")
    current_date = user_now.date()

    # Duration check
    start_date = datetime.fromisoformat(item["StartDate"]).date()
    duration_days = int(item["DurationDays"])
    end_date = start_date + timedelta(days=duration_days)


    if not (start_date <= current_date < end_date):
        return  # Outside duration window

    # Time match
    if current_time_str not in reminder_times:
        return

    # SEND EMAIL
    send_email(email, med_name, current_time_str, timezone_name)

# ======================================================
# SES EMAIL
# ======================================================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ses = boto3.client("ses", region_name="us-east-1")  # change region if needed

SENDER_EMAIL = "YOUR_Email_ID"  # must be verified in SES

def send_email(email, medication, time_str, tz):
    subject = "Medication Reminder"

    body_text = (
        "Medication Reminder\n\n"
        "It's time to take your medication:\n\n"
        f"💊 {medication}\n"
        f"⏰ Time: {time_str} ({tz})\n\n"
        "Stay healthy!"
    )

    try:
        response = ses.send_email(
            Source=SENDER_EMAIL,
            Destination={
                "ToAddresses": [email]   # ✅ sends ONLY to this user
            },
            Message={
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8"
                },
                "Body": {
                    "Text": {
                        "Data": body_text,
                        "Charset": "UTF-8"
                    }
                }
            }
        )


        logger.info(f"Email sent to {email} for {medication}. MessageId={response['MessageId']}")

    except Exception as e:
        logger.error(f"Failed to send email to {email}: {str(e)}")











