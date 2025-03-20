from app import mail
from flask_mail import Message


def send_email(recipients, subject, template):
    msg = Message(
        subject,
        recipients=recipients,
        html=template,
        sender="wildmarker@nkn.uidaho.edu",
    )
    mail.send(msg)
