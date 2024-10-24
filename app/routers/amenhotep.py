# app/routers/amenhotep.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, database, oauth2
from ..ai_chat.amenhotep import AmenhotepAI
from typing import List

router = APIRouter(prefix="/amenhotep", tags=["Amenhotep Chat"])


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    amenhotep = AmenhotepAI()
    await websocket.accept()

    try:
        # إرسال رسالة الترحيب
        await websocket.send_text(amenhotep.get_welcome_message())

        while True:
            # استقبال رسالة من المستخدم
            message = await websocket.receive_text()

            # حفظ الرسالة في قاعدة البيانات
            db_message = models.AmenhotepMessage(user_id=user_id, message=message)
            db.add(db_message)
            db.commit()

            # الحصول على الرد من النموذج
            response = await amenhotep.get_response(message)

            # حفظ الرد في قاعدة البيانات
            db_message.response = response
            db.commit()

            # إرسال الرد للمستخدم
            await websocket.send_text(response)

    except WebSocketDisconnect:
        print(f"Client #{user_id} disconnected")
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        await websocket.close()
