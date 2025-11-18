from firebase_admin import credentials, messaging, initialize_app
from app.core.config import settings
from typing import List
import logging

logger = logging.getLogger(__name__)


def initialize_firebase():
    """
    Initialize Firebase using service account credentials and configuration from settings.

    Returns:
        bool: True if initialization is successful, False otherwise.
    """
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
    """
    Send a multicast push notification to multiple device tokens.

    Parameters:
        tokens (List[str]): List of device tokens.
        title (str): Notification title.
        body (str): Notification body.
        data (dict, optional): Additional data payload.

    Returns:
        messaging.BatchResponse or None: The response from Firebase or None on error.
    """
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
    """
    Send a push notification to a specific topic.

    Parameters:
        topic (str): The topic name.
        title (str): Notification title.
        body (str): Notification body.
        data (dict, optional): Additional data payload.

    Returns:
        str or None: The message ID on success or None on error.
    """
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
    """
    Subscribe devices to a specified topic.

    Parameters:
        tokens (List[str]): List of device tokens.
        topic (str): The topic to subscribe to.

    Returns:
        messaging.TopicManagementResponse or None: The response or None on error.
    """
    try:
        response = messaging.subscribe_to_topic(tokens, topic)
        return response
    except Exception as e:
        logger.error(f"Error subscribing to topic: {str(e)}")
        return None


def unsubscribe_from_topic(tokens: List[str], topic: str):
    """
    Unsubscribe devices from a specified topic.

    Parameters:
        tokens (List[str]): List of device tokens.
        topic (str): The topic to unsubscribe from.

    Returns:
        messaging.TopicManagementResponse or None: The response or None on error.
    """
    try:
        response = messaging.unsubscribe_from_topic(tokens, topic)
        return response
    except Exception as e:
        logger.error(f"Error unsubscribing from topic: {str(e)}")
        return None


def send_push_notification(token: str, title: str, body: str, data: dict = None):
    """
    Send a push notification to a single device.

    Parameters:
        token (str): The device token.
        title (str): Notification title.
        body (str): Notification body.
        data (dict, optional): Additional data payload.

    Returns:
        str or None: The message ID on success or None on error.
    """
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
        )
        response = messaging.send(message)
        logger.info(f"Successfully sent message: {response}")
        return response
    except Exception as e:
        logger.error(f"Error sending push notification: {str(e)}")
        return None
