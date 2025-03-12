"""
Amenhotep Chat Router Module
This module provides endpoints for chatting with Amenhotep AI.
It includes WebSocket endpoints for real-time chat, endpoints for retrieving
chat history, and for clearing the conversation history.
"""

# =====================================================
# ==================== Imports ========================
# =====================================================
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

# Local imports
from .. import models, schemas, oauth2
from ..database import get_db
from ..ai_chat.amenhotep import AmenhotepAI

# =====================================================
# =============== Global Variables ====================
# =====================================================
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/amenhotep", tags=["Amenhotep Chat"])

# =====================================================
# ================ WebSocket Endpoints =================
# =====================================================


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    WebSocket endpoint for real-time chat with Amenhotep AI.

    Parameters:
        - websocket: The WebSocket connection.
        - user_id: ID of the user initiating the chat.
        - db: Database session.
        - current_user: The authenticated user.

    Workflow:
        1. Accept the WebSocket connection.
        2. Instantiate the Amenhotep AI chatbot.
        3. Send a welcome message.
        4. Enter a loop to receive messages, store them in DB, get AI response,
           update the message record, and send the response back.
    """
    try:
        # Accept the WebSocket connection
        await websocket.accept()
        logger.info(f"New WebSocket connection established for user {user_id}")

        # Initialize Amenhotep AI (using the imported class)
        amenhotep = AmenhotepAI()

        # Send welcome message
        await websocket.send_text(amenhotep.welcome_message)

        # Main chat loop
        while True:
            try:
                # Receive message from the client
                message = await websocket.receive_text()
                logger.debug(f"Received message from user {user_id}: {message}")

                if not message:
                    logger.warning(f"Empty message received from user {user_id}")
                    continue

                # Create and store the message in the database
                db_message = models.AmenhotepMessage(user_id=user_id, message=message)
                db.add(db_message)
                db.commit()
                logger.debug(f"Message saved to database for user {user_id}")

                # Get response from Amenhotep AI (note: get_response expects user_id and message)
                response = await amenhotep.get_response(user_id, message)
                logger.debug(f"Generated response for user {user_id}: {response}")

                # Update the database record with the AI response
                db_message.response = response
                db.commit()
                logger.debug(f"Response saved to database for user {user_id}")

                # Send the AI response back to the client
                await websocket.send_text(response)
                logger.debug(f"Response sent to user {user_id}")

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for user {user_id}")
                break
            except Exception as e:
                logger.error(f"Error processing message for user {user_id}: {str(e)}")
                error_message = (
                    "عذراً، حدث خطأ في معالجة رسالتك. هل يمكنك المحاولة مرة أخرى؟"
                )
                await websocket.send_text(error_message)

    except Exception as e:
        logger.error(f"Error in WebSocket connection for user {user_id}: {str(e)}")
        if websocket.client_state.connected:
            await websocket.close(code=1011, reason="Internal server error")
    finally:
        # Cleanup: Ensure the WebSocket is closed
        if websocket.client_state.connected:
            await websocket.close()
        logger.info(f"WebSocket connection closed for user {user_id}")


# =====================================================
# ============== Chat History Endpoints ===============
# =====================================================


@router.get("/chat-history/{user_id}", response_model=List[schemas.AmenhotepMessageOut])
async def get_chat_history(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve the chat history for a specified user.

    Access is allowed if the current user is the owner or an admin.
    """
    try:
        if current_user.id != user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=403, detail="غير مصرح لك بالوصول إلى سجل المحادثة هذا"
            )

        messages = (
            db.query(models.AmenhotepMessage)
            .filter(models.AmenhotepMessage.user_id == user_id)
            .order_by(models.AmenhotepMessage.created_at.desc())
            .all()
        )
        logger.info(f"Retrieved chat history for user {user_id}")
        return messages
    except Exception as e:
        logger.error(f"Error retrieving chat history for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="حدث خطأ أثناء استرجاع سجل المحادثة"
        )


@router.delete("/clear-history/{user_id}")
async def clear_chat_history(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Clear the chat history for a specified user.

    Access is allowed if the current user is the owner or an admin.
    """
    try:
        if current_user.id != user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=403, detail="غير مصرح لك بمسح سجل المحادثة هذا"
            )

        db.query(models.AmenhotepMessage).filter(
            models.AmenhotepMessage.user_id == user_id
        ).delete()
        db.commit()
        logger.info(f"Cleared chat history for user {user_id}")
        return {"message": "تم مسح سجل المحادثة بنجاح"}
    except Exception as e:
        logger.error(f"Error clearing chat history for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء مسح سجل المحادثة")


# =====================================================
# =========== Additional MessageRouter Class =========
# =====================================================
# Note: The following class provides an alternative WebSocket endpoint.
# It is kept for backward compatibility or additional functionality.
# Ensure that the get_response method is called with the required user_id parameter.


class MessageRouter:
    def __init__(self):
        self.amenhotep = AmenhotepAI()

    @router.websocket("/ws/amenhotep/{user_id}")
    async def amenhotep_chat(self, websocket: WebSocket, user_id: int):
        """
        Alternative WebSocket endpoint for Amenhotep chat.
        This version does not interact with the database.

        Parameters:
            - websocket: The WebSocket connection.
            - user_id: The user's ID.
        """
        try:
            await websocket.accept()
            # Send welcome message
            await websocket.send_text(self.amenhotep.welcome_message)
            while True:
                message = await websocket.receive_text()
                # Call get_response with both user_id and message
                response = await self.amenhotep.get_response(user_id, message)
                await websocket.send_text(response)
        except WebSocketDisconnect:
            logger.info(f"User {user_id} disconnected from Amenhotep chat")
        except Exception as e:
            logger.error(
                f"Error in alternative chat endpoint for user {user_id}: {str(e)}"
            )
            if websocket.client_state.connected:
                await websocket.close(code=1011, reason="Internal server error")
