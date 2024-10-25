"""
Amenhotep Chat Router Module
يوفر نقاط النهاية لخدمة المحادثة مع أمنحتب الثالث AI
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, database, oauth2
from ..ai_chat.amenhotep import AmenhotepAI
import logging

# إعداد التسجيل
logger = logging.getLogger(__name__)

# تكوين الموجه
router = APIRouter(prefix="/amenhotep", tags=["Amenhotep Chat"])


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    نقطة نهاية WebSocket للمحادثة مع أمنحتب

    Parameters:
        websocket: اتصال WebSocket
        user_id: معرف المستخدم
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي المصادق عليه
    """
    try:
        # قبول اتصال WebSocket
        await websocket.accept()
        logger.info(f"New WebSocket connection established for user {user_id}")

        # تهيئة أمنحتب AI
        amenhotep = models.AmenhotepAI()

        # إرسال رسالة الترحيب
        await websocket.send_text(amenhotep.welcome_message)

        # حلقة المحادثة الرئيسية
        while True:
            try:
                # استقبال رسالة من المستخدم
                message = await websocket.receive_text()
                logger.debug(f"Received message from user {user_id}: {message}")

                # التحقق من صحة الرسالة
                if not message:
                    logger.warning(f"Empty message received from user {user_id}")
                    continue

                # إنشاء سجل رسالة في قاعدة البيانات
                db_message = models.AmenhotepMessage(user_id=user_id, message=message)
                db.add(db_message)
                db.commit()
                logger.debug(f"Message saved to database for user {user_id}")

                # الحصول على رد من أمنحتب
                response = await amenhotep.get_response(user_id, message)
                logger.debug(f"Generated response for user {user_id}: {response}")

                # تحديث سجل الرسالة بالرد
                db_message.response = response
                db.commit()
                logger.debug(f"Response saved to database for user {user_id}")

                # إرسال الرد للمستخدم
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
        # التنظيف والإغلاق
        if websocket.client_state.connected:
            await websocket.close()
        logger.info(f"WebSocket connection closed for user {user_id}")


@router.get("/chat-history/{user_id}", response_model=List[models.AmenhotepMessage])
async def get_chat_history(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    استرجاع سجل المحادثة للمستخدم المحدد

    Parameters:
        user_id: معرف المستخدم
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي المصادق عليه

    Returns:
        List[AmenhotepMessage]: قائمة برسائل المحادثة
    """
    try:
        # التحقق من الصلاحيات
        if current_user.id != user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=403, detail="غير مصرح لك بالوصول إلى سجل المحادثة هذا"
            )

        # استرجاع السجل
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
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    مسح سجل محادثة المستخدم المحدد

    Parameters:
        user_id: معرف المستخدم
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي المصادق عليه
    """
    try:
        # التحقق من الصلاحيات
        if current_user.id != user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=403, detail="غير مصرح لك بمسح سجل المحادثة هذا"
            )

        # حذف السجل
        db.query(models.AmenhotepMessage).filter(
            models.AmenhotepMessage.user_id == user_id
        ).delete()
        db.commit()

        logger.info(f"Cleared chat history for user {user_id}")
        return {"message": "تم مسح سجل المحادثة بنجاح"}

    except Exception as e:
        logger.error(f"Error clearing chat history for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="حدث خطأ أثناء مسح سجل المحادثة")
