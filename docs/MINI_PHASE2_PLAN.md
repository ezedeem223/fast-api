# Phase 2 – Mini Plan Progress Report

## أين وصلنا؟
- Routers الخاصة بالمنشورات والتعليقات أصبحت نحيفة؛ جميع المنطق التجاري تقريباً انتقل إلى الخدمات (`PostService`, `CommentService`).
- المخططات الضخمة بدأت تنتقل من `app/schemas.py` إلى حزم النطاقات:  
  - مخططات المنشورات والتعليقات في `app/modules/posts/schemas.py`.  
  - مخططات المستخدم في `app/modules/users/schemas.py`.  
  - إنشاء ملف أولي لـ `app/modules/messaging/schemas.py` وبدأ نقل مخططات الرسائل/مشاركة الشاشة إليه.
- `docs/REFACTOR_CHANGELOG.md` يُحدَّث بعد كل نقل لضمان تتبع خطوط إعادة الهيكلة.
- اختبارات `tests/test_posts.py` تُستخدم كاختبار دخان بعد كل مرحلة لنضمن عدم حدوث تراجعات أثناء التفكيك.

## أين توقفنا؟
- ما زالت `app/schemas.py` تحتوي على:
  - تعداد `MessageType` و `SortOrder`.
  - بقايا مخططات المراسلة (نماذج البحث/النتائج، نماذج مشاركة الشاشة) التي ينبغي أن تنتقل بالكامل إلى `app/modules/messaging/schemas.py`.
  - مخططات أخرى (الرسائل، المحتوى العام، الاستدعاءات) التي ستُنقل لاحقاً حسب الخطة.
- لم تُشغَّل اختبارات نطاق المراسلة بعد (مثل `tests/test_message.py`) لأن مخططات الرسائل ليست مكتملة النقل.

## ما التالي؟
1. **إكمال نقل مخططات المراسلة**:
   - نقل `MessageType`, `SortOrder`, `MessageSearch`, `MessageSearchResponse`, `MessageUpdate`, `MessageOut`, نماذج مشاركة الشاشة… إلى `app/modules/messaging/schemas.py`.
   - تحديث الاستيرادات في `app/routers/message.py`, الخدمات، وبقية الوحدات.
   - تشغيل `python -m pytest tests/test_message.py` (وملفات مترابطة إذا لزم) للتأكد من سلامة وظائف المراسلة.
2. **الاستمرار في تفكيك `app/schemas.py`** حسب الخطة الكبرى:
   - اختيار نطاق جديد (مثل مخططات المجتمع أو الدعم) ونقلها إلى `app/modules/<domain>/schemas.py`.
   - توثيق كل خطوة في `docs/REFACTOR_CHANGELOG.md`.
3. **التحقق المستمر بالاختبارات** بعد كل دفعة:  
   - `tests/test_posts.py` تمثل دخان عام.  
   - إضافة اختبارات نطاقية (users, messaging, community) كلما تم نقل مخططاتهم لضمان عدم حدوث تراجعات.

هذا الملف يُحدَّث بعد كل تقدم ملموس ليبقى الفريق على دراية بموقع العمل ضمن الخطة الكبرى.
