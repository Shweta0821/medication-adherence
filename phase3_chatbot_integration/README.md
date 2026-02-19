# 💊 Medication Reminder Bot (AWS Serverless)

A fully serverless Medication Reminder system built using **Amazon Lex V2**, **AWS Lambda**, **DynamoDB**, **Amazon SES**, and **Amazon EventBridge**.

This project allows users to:

- ✅ Create medication reminders
- 📋 View active reminders
- 🛑 Stop reminders
- 📧 Receive email notifications at the correct scheduled time

---

## 🏗️ Architecture Overview

```
User → Amazon Lex V2 → Lambda (Bot Handler)
                             ↓
                        DynamoDB
                             ↓
                      Amazon SES (Email Subscription)

EventBridge (Scheduled Trigger)
             ↓
     Lambda (Reminder Processor)
             ↓
        Amazon SES (Send Email)
```

---

## ⚙️ Services Used

| Service | Purpose |
|---|---|
| Amazon Lex V2 | Conversational chatbot interface |
| AWS Lambda | Business logic processing |
| Amazon DynamoDB | Store medication reminders |
| Amazon SES | Send email notifications |
| Amazon EventBridge | Trigger reminder Lambda every minute |

---

## 🧠 System Flow

### 1️⃣ Create Medication Reminder

- User interacts with Lex V2 Bot
- Lambda function:
  - Validates input
  - Stores reminder in DynamoDB
  - Subscribes user email using SES
  - Confirmation message returned to user

**Stored DynamoDB Item Example:**

```json
{
  "UserEmail": "user@example.com",
  "ReminderId": "MED#uuid",
  "MedicationName": "Vitamin D",
  "Frequency": "once",
  "ReminderTimes": ["08:00"],
  "DurationDays": 30,
  "Timezone": "America/Denver",
  "Status": "ACTIVE",
  "StartDate": "2026-02-01T00:00:00"
}
```

### 2️⃣ View Medication Reminders

- Queries DynamoDB using `UserEmail`
- Filters records with `Status = ACTIVE`
- Returns formatted reminder list to user

### 3️⃣ Stop Medication Reminder

- Confirms medication name
- Updates `Status = STOPPED` in DynamoDB
- Sends confirmation message to user

---

## ⏰ Email Reminder System

A separate Lambda function is triggered by **EventBridge every 1 minute**.

**Flow:**

1. EventBridge sends current UTC time
2. Lambda:
   - Reads all `ACTIVE` reminders
   - Converts UTC time → User's stored timezone
   - Matches reminder time
   - Sends email using SES if matched

---

## 🌍 Timezone Handling

User timezone is stored in full **IANA format**. Examples:

- `America/New_York`
- `America/Denver`
- `America/Los_Angeles`

> EventBridge runs in UTC. The Reminder Lambda converts UTC → User timezone before matching time, ensuring correct delivery across time zones.

---

## 📧 Amazon SES Setup (Personal Project)

Since this is a personal project:

- SES is used in **Sandbox Mode**
- Sender email must be verified
- Recipient email must also be verified *(Sandbox requirement)*

**SES Configuration Steps:**

1. Go to **Amazon SES Console**
2. Navigate to **Verified Identities**
3. Click **Create Identity**
4. Choose **Email Address** *(no domain required)*
5. Verify email from inbox
6. Use verified email as `Source` in Lambda

---

## 🔁 EventBridge Configuration

1. Go to **Amazon EventBridge**
2. Create Rule:
   - Schedule pattern
   - `rate(1 minute)`
3. Target:
   - Reminder Lambda function

---

## 🔐 IAM Permissions Required

**Bot Lambda Role:**
- `AmazonDynamoDBFullAccess`
- `AmazonSESFullAccess`

**Reminder Lambda Role:**
- `AmazonDynamoDBReadOnlyAccess`
- `AmazonSESFullAccess`

---

## 🧪 Testing Strategy

**Lex Testing:**
- Test Create / View / Stop flows
- Validate multiple medications
- Confirm status updates

**Reminder Lambda Testing** — use test event:

```json
{
  "time": "2026-02-05T12:00:00Z"
}
```

---

## 📌 Key Features

- Fully serverless architecture
- Timezone-aware reminders
- SES-based secure email sending
- Scalable DynamoDB storage
- Modular Lambda functions
- Event-driven scheduling

---

## 🚀 Future Enhancements

- Move SES out of sandbox mode
- Add SMS notifications
- Add medication history tracking
- Add user authentication
- Add frontend dashboard

---

## 🏁 Conclusion

This project demonstrates:

- Event-driven serverless design
- Multi-service AWS integration
- Timezone-aware scheduling
- Email notification system using SES
- Conversational AI using Lex V2

A complete real-world AWS serverless implementation for automated medication reminders.
