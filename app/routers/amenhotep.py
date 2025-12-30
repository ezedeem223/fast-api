"""Amenhotep AI router for chatbot interactions and analytics hooks."""

# =====================================================
# ==================== Imports ========================
# =====================================================
import logging
from typing import List

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import i18n
from app.core.database import get_db
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

# Local imports
from .. import models, oauth2, schemas
from ..ai_chat.amenhotep import AmenhotepAI

# =====================================================
# =============== Global Variables ====================
# =====================================================
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/amenhotep", tags=["Amenhotep Chat"])
DEFAULT_FALLBACK_LANG = "en"


class AmenhotepAskRequest(BaseModel):
    message: str = Field(..., min_length=1)
    language: str | None = None


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
                    await websocket.close(code=1003, reason="Empty message")
                    break

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
                error_message = "Sorry, there was an error processing your message. Please try again."
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
                status_code=403,
                detail="You are not authorized to access this chat history.",
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
            status_code=500,
            detail="An error occurred while retrieving the chat history.",
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
                status_code=403,
                detail="You are not authorized to clear this chat history.",
            )

        db.query(models.AmenhotepMessage).filter(
            models.AmenhotepMessage.user_id == user_id
        ).delete()
        db.commit()
        logger.info(f"Cleared chat history for user {user_id}")
        return {"message": "Chat history cleared successfully."}
    except Exception as e:
        logger.error(f"Error clearing chat history for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while clearing the chat history.",
        )


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
        """Endpoint: amenhotep_chat."""
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


@router.post("/ask")
async def ask_amenhotep(
    payload: AmenhotepAskRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """HTTP endpoint to ask Amenhotep; validates empty input and applies language fallback."""
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    default_lang = getattr(request.app.state, "default_language", DEFAULT_FALLBACK_LANG)
    preferred = payload.language or getattr(current_user, "preferred_language", None)
    language = preferred if preferred in i18n.ALL_LANGUAGES else default_lang

    bot = AmenhotepAI()
    response = await bot.get_response(current_user.id, message)

    record = models.AmenhotepMessage(
        user_id=current_user.id, message=message, response=response
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {"response": response, "language": language, "id": record.id}
