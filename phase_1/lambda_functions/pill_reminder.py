import json

import boto3
import datetime
from zoneinfo import ZoneInfo  # built-in, no need to install

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

TABLE_NAME = "MedicationSchedules"
TOPIC_ARN = "arn:aws:sns:us-east-1:342593763220:PillReminderTopic"  # Replace with your ARN

def lambda_handler(event, context):
    table = dynamodb.Table(TABLE_NAME)

    # Current UTC time
    utc_now = datetime.datetime.now(datetime.timezone.utc)

    # Convert to Mountain Time (America/Denver handles DST automatically)
    local_now = utc_now.astimezone(ZoneInfo("America/Los_Angeles"))

    # Format to match DynamoDB (YYYY-MM-DDTHH:MM)
    #now_str = local_now.strftime("%Y-%m-%dT%H:%M")
    now_str = local_now.strftime("%H:%M")

    # Scan DynamoDB for items matching current time
    response = table.scan(
        FilterExpression="MedicationTime = :t",
        ExpressionAttributeValues={":t": now_str}
    )

    items = response.get("Items", [])
    print(f"Checking for reminders at {now_str}, found {len(items)} items")

    for item in items:
        message = f"Reminder: Take {item['MedicationName']} {item['Dosage']}"
        sns.publish(
            TopicArn=TOPIC_ARN,
            Message=message,
            Subject="Pill Reminder"
        )
        print(f"Sent reminder for {item['MedicationName']} to {item['Contact']}")

    return {"status": "done", "count": len(items)}
