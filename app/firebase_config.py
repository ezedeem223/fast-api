"""Firebase initialization and notification helpers with graceful failure logging.

Integration details:
- Reads Firebase identifiers and secrets from `settings` (env-backed).
- Expects `firebase_api_key` to be a raw private key string for service account auth.
- Falls back to no-op on initialization failures so the app can start without FCM.
"""

from firebase_admin import credentials, messaging, initialize_app, storage
from app.core.config import settings
from typing import List
import logging

logger = logging.getLogger(__name__)

# Compatibility: some firebase_admin versions expose only send_each_for_multicast.
if not hasattr(messaging, "send_multicast"):
    messaging.send_multicast = messaging.send_each_for_multicast  # type: ignore[attr-defined]


def initialize_firebase():
    """Initialize Firebase using service account credentials and config from env-backed settings.

    Returns True on successful bootstrap; returns False and logs when credentials are absent/invalid
    so non-notification code paths remain operational.
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
        # Fail open: log and return False so the rest of the app can run without push notifications.
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


# ----------------------- Storage utilities ----------------------- #

def upload_file_to_bucket(bucket_name: str, source_file: str, destination_blob: str) -> bool:
    """Upload a local file to Firebase Storage; returns True on success, False on failure."""
    try:
        bucket = storage.bucket(bucket_name)
        blob = bucket.blob(destination_blob)
        blob.upload_from_filename(source_file)
        return True
    except Exception as exc:  # pragma: no cover - exercised via tests with dummy storage
        logger.error("Failed to upload file to bucket %s: %s", bucket_name, exc)
        return False


def generate_signed_url(bucket_name: str, blob_name: str, expires_in_seconds: int = 3600) -> str | None:
    """Generate a signed URL for a blob; returns None on failure."""
    try:
        bucket = storage.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.generate_signed_url(expires_in_seconds)
    except Exception as exc:  # pragma: no cover - exercised via tests with dummy storage
        logger.error("Failed to generate signed URL for %s: %s", blob_name, exc)
        return None


def delete_file_from_bucket(bucket_name: str, blob_name: str) -> bool:
    """Delete a blob from Firebase Storage; returns True on success, False otherwise."""
    try:
        bucket = storage.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
        return True
    except Exception as exc:  # pragma: no cover - exercised via tests with dummy storage
        logger.error("Failed to delete blob %s: %s", blob_name, exc)
        return False
