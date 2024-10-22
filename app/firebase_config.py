import firebase_admin
from firebase_admin import credentials, messaging, initialize_app
from pathlib import Path
from .config import settings
from typing import List
import logging

logger = logging.getLogger(__name__)


def initialize_firebase():
    """Initialize Firebase with the configuration from settings"""
    try:
        cred = credentials.Certificate(
            {
                "type": "service_account",
                "project_id": settings.firebase_project_id,
                "private_key": settings.firebase_api_key,
                "client_email": f"firebase-adminsdk@{settings.firebase_project_id}.iam.gserviceaccount.com",
            }
        )

        firebase_config = {
            "apiKey": settings.firebase_api_key,
            "authDomain": settings.firebase_auth_domain,
            "projectId": settings.firebase_project_id,
            "storageBucket": settings.firebase_storage_bucket,
            "messagingSenderId": settings.firebase_messaging_sender_id,
            "appId": settings.firebase_app_id,
            "measurementId": settings.firebase_measurement_id,
        }

        initialize_app(cred, firebase_config)
        logger.info("Firebase initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {str(e)}")
        return False


def send_multicast_notification(
    tokens: List[str], title: str, body: str, data: dict = None
):
    """إرسال إشعار لعدة أجهزة"""
    try:
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
        )
        response = messaging.send_multicast(message)
        return response
    except Exception as e:
        logger.error(f"Error sending multicast notification: {str(e)}")
        return None


def send_topic_notification(topic: str, title: str, body: str, data: dict = None):
    """إرسال إشعار لموضوع معين"""
    try:
        message = messaging.Message(
            topic=topic,
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
        )
        response = messaging.send(message)
        return response
    except Exception as e:
        logger.error(f"Error sending topic notification: {str(e)}")
        return None


def subscribe_to_topic(tokens: List[str], topic: str):
    """اشتراك أجهزة في موضوع"""
    try:
        response = messaging.subscribe_to_topic(tokens, topic)
        return response
    except Exception as e:
        logger.error(f"Error subscribing to topic: {str(e)}")
        return None


def unsubscribe_from_topic(tokens: List[str], topic: str):
    """إلغاء اشتراك أجهزة من موضوع"""
    try:
        response = messaging.unsubscribe_from_topic(tokens, topic)
        return response
    except Exception as e:
        logger.error(f"Error unsubscribing from topic: {str(e)}")
        return None


def send_push_notification(token: str, title: str, body: str, data: dict = None):
    """Send a push notification to a specific device"""
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=token,
        )
        response = messaging.send(message)
        logger.info(f"Successfully sent message: {response}")
        return response
    except Exception as e:
        logger.error(f"Error sending push notification: {str(e)}")
        return None
