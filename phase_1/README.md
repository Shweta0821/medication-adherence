**Goal:** Take medication schedule from sample data and send SNS notifications at scheduled times.

1. Create DynamoDB Table

2. Load Sample Data into DynamoDB

3. Create SNS Topic

4. Create Lambda Function

5. Set EventBridge Rule (Scheduler)

6. Test End-to-End

**What happens:**
Lambda runs at 10:00 → finds user1’s row → publishes “Reminder: Metformin 500mg at 22:00” to SNS → you get an email.

**What you achieve**
A fully working automated reminder system where users get SMS/email notifications at their medication times.

All triggered without any manual intervention.

Useful for personal reminders or as a proof-of-concept project.
