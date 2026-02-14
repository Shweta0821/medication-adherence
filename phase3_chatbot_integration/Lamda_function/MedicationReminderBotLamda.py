import json
import boto3
import uuid
import logging
import re
from datetime import datetime
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

# ======================================================
# SETUP
# ======================================================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("MedicationReminderBot")

# sns = boto3.client("sns")
# SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:342593763220:MedicationReminderBotTopic" # Ensure this is your actual ARN
# Initialize clients
ses = boto3.client("ses", region_name="us-east-1")

# ======================================================
# MAIN HANDLER
# ======================================================
def lambda_handler(event, context):
    logger.info(json.dumps(event))

    intent = event["sessionState"]["intent"]
    intent_name = intent["name"]
    invocation_source = event.get("invocationSource")
    slots = intent.get("slots", {})

    # --- 1. THE LOOP INTERCEPTOR (CRITICAL FIX) ---
    # We check this at the very top so it works for both Dialog and Fulfillment hooks.
    add_more_raw = get(slots, "add_more")
    if add_more_raw:
        val = str(add_more_raw).lower()
        if val in ["confirmed", "yes", "true", "yeah", "yep"]:
            return reset_for_next_med(slots)
       
        # If they said "No" (Denied), we let it fall through to Fulfillment.

    # 2. Routing
    if intent_name == "ViewMedicationReminders":
        return handle_view(slots)

    if intent_name == "StopMedicationReminder":
        return handle_stop(slots)

    if intent_name == "CreateMedicationReminderIntent":
        if invocation_source == "DialogCodeHook":
            return handle_add_dialog(slots)
        if invocation_source == "FulfillmentCodeHook":
            return handle_add_fulfillment(slots)


    return close(intent_name, "Fulfilled", "I'm sorry, something went wrong.")

# ======================================================
# ADD MEDICATION — DIALOG
# ======================================================
def handle_add_dialog(slots):
    # Validation
    validation = validate_slots(slots)
    if not validation["isValid"]:
        return elicit_slot("CreateMedicationReminderIntent", validation["violatedSlot"], validation["message"], slots)

    # Frequency Logic
    freq = get(slots, "med_frequency")
    t1 = get(slots, "med_time_1")
    t2 = get(slots, "med_time_2")
    t3 = get(slots, "med_time_3")

    if freq:
        freq = freq.lower()
        if freq == "twice" and t1 and not t2:
            return elicit_slot("CreateMedicationReminderIntent", "med_time_2", "What is the second dose time?", slots)
        if freq == "thrice":
            if t1 and not t2:
                return elicit_slot("CreateMedicationReminderIntent", "med_time_2", "What is the second dose time?", slots)
            if t2 and not t3:
                return elicit_slot("CreateMedicationReminderIntent", "med_time_3", "What is the third dose time?", slots)



    # --- SAVE LOGIC ---
    # If med details are in but we haven't asked "add_more" yet, save and ask.
    if (get(slots, "med_name") and get(slots, "med_frequency") and
        get(slots, "med_time_1") and get(slots, "med_duration") and not get(slots, "add_more")):
       
        save_or_update(slots)
       
        # We trigger an ElicitSlot for 'add_more' to keep the session in DialogHook
        return elicit_slot(
            "CreateMedicationReminderIntent",
            "add_more",
            f"I've saved {get(slots, 'med_name')}. Would you like to add another medication?",
            slots
        )


    return delegate("CreateMedicationReminderIntent", slots)


# ======================================================
# ADD MEDICATION — FULFILLMENT
# ======================================================
def handle_add_fulfillment(slots):
    # This runs when the user says "No" to adding more
    email = get(slots, 'email')
    return close(
        "CreateMedicationReminderIntent",
        "Fulfilled",
        f"All your medications have been saved. Notifications will be sent to {email}.\n Choose an action below: View Medication or Stop Medication."
    )


# ======================================================
# RESET FOR NEXT MEDICATION (THE FIX)
# ======================================================
def reset_for_next_med(slots):
    # We must preserve the identity slots but set the value part of the med slots to None.
    # We return the slots in the exact Lex V2 structure.
   
    # Identify slots to keep
    user_name_obj = slots.get("user_name")
    email_obj = slots.get("email")
    timezone_obj = slots.get("timezone")


    # Construct clean slot map
    # Setting a slot to None (null) tells Lex it needs to be filled again.
    new_slots = {
        "user_name": user_name_obj,
        "email": email_obj,
        "timezone": timezone_obj,
        "med_name": None,
        "med_frequency": None,
        "med_time_1": None,
        "med_time_2": None,
        "med_time_3": None,
        "med_duration": None,
        "add_more": None
    }



    return {
        "sessionState": {
            "dialogAction": {
                "type": "ElicitSlot",
                "slotToElicit": "med_name"
            },
            "intent": {
                "name": "CreateMedicationReminderIntent",
                "slots": new_slots,
                "state": "InProgress" # Force state away from 'ReadyForFulfillment'
            }
        },
        "messages": [
            {
                "contentType": "PlainText",
                "content": "Sure! What is the name of the next medication?"
            }
        ]
    }



def save_or_update(slots):
    email = get(slots, "email")
    med_name = get(slots, "med_name")
    times = [t for t in [get(slots, "med_time_1"), get(slots, "med_time_2"), get(slots, "med_time_3")] if t]
   
    # 1. Get all existing records for this email
    res = table.query(KeyConditionExpression=Key("UserEmail").eq(email))
    items = res.get("Items", []) # This is the variable name you need
   
    # 2. Check if the user is ALREADY subscribed in any existing record
    already_subscribed = any(i.get("EmailSubscribed") is True for i in items)
   
    # 3. Check if this specific medication already exists
    match = next((i for i in items if i.get("MedicationName", "").lower() == med_name.lower()), None)


    if match:
        # Update existing medication
        rid = match["ReminderId"] # Extract for the verification call later
        table.update_item(
            Key={"UserEmail": email, "ReminderId": rid},
            UpdateExpression="SET Frequency = :f, ReminderTimes = :t, DurationDays = :d, #st = :s, EmailSubscribed = :es",
            ExpressionAttributeNames={"#st": "Status"},
            ExpressionAttributeValues={
                ":f": get(slots, "med_frequency"),
                ":t": times,
                ":d": int(get(slots, "med_duration")),
                ":s": "ACTIVE",
                ":es": already_subscribed
            }
        )
    else:
        # Create new medication
        rid = f"MED#{uuid.uuid4()}"
        table.put_item(Item={
            "UserEmail": email,
            "ReminderId": rid,
            "UserName": get(slots, "user_name"),
            "Timezone": get(slots, "timezone"),
            "MedicationName": med_name,
            "Frequency": get(slots, "med_frequency"),
            "ReminderTimes": times,
            "DurationDays": int(get(slots, "med_duration")),
            "Status": "ACTIVE",
            "StartDate": datetime.utcnow().isoformat(),
            "EmailSubscribed": already_subscribed
        })


    # 4. Trigger SES onboarding if this is the user's first time
    if not already_subscribed:
        # Pass 'items' here instead of 'existing_items'
        verify_ses_email_once(email, rid, items)


def verify_ses_email_once(email, rid, existing_items):
    """
    Checks if the user has been 'onboarded' for SES.
    If not, triggers a verification email and updates DynamoDB.
    """
    # Double check the list provided
    if any(i.get("EmailSubscribed") for i in existing_items):
        logger.info(f"User {email} already verified in SES.")
        return


    try:
        # Trigger SES Verification
        ses.verify_email_identity(EmailAddress=email)
        logger.info(f"Verification email sent to {email}")


        # Mark the record in DynamoDB so we don't spam verification requests
        table.update_item(
            Key={"UserEmail": email, "ReminderId": rid},
            UpdateExpression="SET EmailSubscribed = :v",
            ExpressionAttributeValues={":v": True}
        )
        logger.info(f"DynamoDB updated: {email} marked as EmailSubscribed=True")


    except Exception as e:
        logger.error(f"SES Identity Verification Error for {email}: {e}")



def handle_view(slots):
    email = get(slots, "email")
    if not email: return delegate("ViewMedicationReminders", slots)
    res = table.query(KeyConditionExpression=Key("UserEmail").eq(email))
    meds = [i for i in res.get("Items", []) if i.get("Status") == "ACTIVE"]
    if not meds: return close("ViewMedicationReminders", "Fulfilled", "No active reminders.")
    lines = [f"{i+1}. {m['MedicationName']} at {', '.join(m['ReminderTimes'])}" for i, m in enumerate(meds)]
    # return close("ViewMedicationReminders", "Fulfilled", "Your Medications:\n" + "\n".join(lines)"\n" + "Choose an action below: Create Medication or Stop Medication.")
    return close(
    "ViewMedicationReminders",
    "Fulfilled",
    "Your Medications:\n" + "\n".join(lines) + "\nChoose an action below: Create Medication or Stop Medication."
    )


def handle_stop(slots):
    email = get(slots, "email")
    med_name = get(slots, "med_name")
    confirm = get(slots, "confirm_stop")


    # 1. Require Email
    if not email:
        return delegate("StopMedicationReminder", slots)


    # 2. Get active meds from DB
    try:
        res = table.query(KeyConditionExpression=Key("UserEmail").eq(email))
        items = res.get("Items", [])
        active = [i for i in items if i.get("Status") == "ACTIVE"]
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return close("StopMedicationReminder", "Failed", "I couldn't access your reminders right now.")


    if not active:
        return close("StopMedicationReminder", "Fulfilled", "You don't have any active medication reminders to stop.")

    # 3. Elicit med_name if missing
    if not med_name:
        med_list = "\n".join([f"- {m.get('MedicationName', 'Unknown')}" for m in active])
        return elicit_slot(
            "StopMedicationReminder",
            "med_name",
            f"Which medication would you like to stop?\n{med_list}",
            slots
        )


    # 4. Find the specific item (Case-insensitive & Safe)
    # Using .get() prevents KeyError if an item is corrupted
    item = next((i for i in active if str(i.get("MedicationName", "")).lower() == str(med_name).lower()), None)


    if not item:
        med_list = ", ".join([m.get('MedicationName', 'Unknown') for m in active])
        return elicit_slot(
            "StopMedicationReminder",
            "med_name",
            f"I couldn't find '{med_name}'. Please choose from: {med_list}",
            slots
        )

    # 5. Handle Confirmation
    if not confirm:
        return elicit_slot(
            "StopMedicationReminder",
            "confirm_stop",
            f"Are you sure you want to stop reminders for {item.get('MedicationName')}?",
            slots
        )

    # Check if they said No
    if str(confirm).lower() in ["denied", "no", "false"]:
        return close("StopMedicationReminder", "Fulfilled", f"Okay, I've kept your {item.get('MedicationName')} reminders active.")


    # 6. Perform the Stop
    try:
        table.update_item(
            Key={"UserEmail": email, "ReminderId": item["ReminderId"]},
            UpdateExpression="SET #s = :st",
            ExpressionAttributeNames={"#s": "Status"},
            ExpressionAttributeValues={":st": "STOPPED"}
        )
        return close("StopMedicationReminder", "Fulfilled", f"Successfully stopped reminders for {item.get('MedicationName')}.Choose an action below: View Medication or Create Medication.")
    except Exception as e:
        logger.error(f"Update Error: {e}")
        return close("StopMedicationReminder", "Failed", "I encountered an error while trying to stop the reminder.")

# ======================================================
# LEX HELPERS
# ======================================================
def get(slots, name):
    slot = slots.get(name)
    if not slot or not slot.get("value"): return None
    return slot["value"].get("interpretedValue") or slot["value"].get("resolvedValues", [None])[0]


def validate_slots(slots):
    email = get(slots, "email")
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return {"isValid": False, "violatedSlot": "email", "message": "Please enter a valid email."}
    return {"isValid": True}


def elicit_slot(intent, slot, message, slots):
    return {
        "sessionState": {
            "dialogAction": {"type": "ElicitSlot", "slotToElicit": slot},
            "intent": {"name": intent, "state": "InProgress", "slots": slots}
        },
        "messages": [{"contentType": "PlainText", "content": message}]
    }


def delegate(intent, slots):
    return {
        "sessionState": {
            "dialogAction": {"type": "Delegate"},
            "intent": {"name": intent, "state": "InProgress", "slots": slots}
        }
    }


def close(intent, state, message):
    return {
        "sessionState": {
            "dialogAction": {"type": "Close"},
            "intent": {"name": intent, "state": state}
        },
        "messages": [{"contentType": "PlainText", "content": message}]
    }














