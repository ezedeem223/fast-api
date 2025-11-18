# Re-Architecture Roadmap (v3)

This roadmap consolidates every improvement we have discussed. Each phase should be completed before moving to the next, with a full `python -m pytest -q` and `python scripts/perf_startup.py` run at the end of each stage.

---

## مرحلة 1 – ضبط الدومينات والتنظيف السطحي
1. **مصادر الإعدادات والبنية**  
   - تحديث جميع الاستخدامات (خصوصاً `app/routers/search.py`) لاستهلاك Redis مباشرة عبر `settings.redis_client`.  
   - تحميل قائمة CORS من إعداد `CORS_ORIGINS` وإعطاء قيمة افتراضية من `settings.cors_origins`.
2. **إزالة الأمثلة والملفات المؤقتة**  
   - حذف الكتل التجريبية (مثل مثال `PostOut` في `app/schemas.py` وملفات `debug_report_*`, `test.db`, مجلدات `uploads/`, `static/media/`).  
   - توسيع `.gitignore` ليشمل الأسرار والملفات المتولدة (Firebase credentials, joblib models, إلخ).
3. **تحسين تسجيل الأحداث ومسارات الصحة**  
   - تحويل WebSocket logging إلى `logging` بدلاً من `print`.  
   - إضافة `/livez` و`/readyz` (مع استعلام DB مبسط) لتسهيل مراقبة الخدمة.

---

## مرحلة 2 – صلابة المنصة وتقليل الترابط
1. **خدمات البحث**  
   - نقل منطق `update_search_statistics` و`update_search_suggestions` من الراوتر إلى خدمة ضمن `app/modules/search/`.  
   - جعل جميع الراوترات/المهام تستهلك الخدمة الجديدة، وتقليل استيراد الراوترات داخل المهام.
2. **التحليلات والمهام الثقيلة**  
   - جعل تحميل `transformers` في `app/analytics.py` كسولاً مع دعم بيئة `APP_ENV=test` لتعطيل Firebase/Amenhotep/scheduler.  
   - تحديث `scripts/perf_startup.py` لتعيين `APP_ENV=test` افتراضياً حتى لا يُشغَّل scheduler أثناء قياس الأداء.
3. **تحسين الميدلوير والأمان**  
   - إعداد `TrustedHostMiddleware`/`HTTPSRedirectMiddleware` (يمكن تفعيلهما في إعدادات الإنتاج لاحقاً) وتجهيز التزمينات اللازمة.  
   - توثيق كيفية إدارة Static/Uploads والأسرار ضمن الإعدادات.

---

## مرحلة 3 – الجودة التشغيلية وتهيئة CI/CD
1. **CI متكامل**  
   - إنشاء سير عمل GitHub Actions (`.github/workflows/ci.yml`) لتشغيل `pytest` و`perf_startup.py` على كل Push/PR، مع `APP_ENV=test`.  
   - إضافة pre-commit hooks (ruff/black) لاحقاً لضمان جودة الكود قبل الدفع.
2. **تحديث الوثائق**  
   - تحديث `docs/DEVELOPER_GUIDE.md` لشرح إعدادات CORS/Redis، المهام الخلفية، مسارات الصحة، وتعليمات Alembic والأسرار.  
   - إضافة README عام في جذر المشروع يشرح الهدف والميزات الأساسية وروابط الوثائق.
3. **تحقق نهائي**  
   - بعد كل مرحلة، تنفيذ `python -m pytest -q`, `python scripts/perf_startup.py --iterations 3 --threshold <env>`، ومراجعة سريعة للأسرار/المفاتيح.

---

# Product & Platform Enhancement Plan

هذه الخطة تركز على تطوير المزايا التشغيلية للمستخدمين، وتقسَّم لثلاث مراحل لضمان التنفيذ المتدرج.

## المرحلة 1 – تجربة التسجيل والمستخدم
1. **Endpoint للتسجيل بكلمة مرور**  
   - إضافة `/register` لإنشاء حساب بكلمة مرور مع إرسال بريد تحقق تلقائي.  
   - التأكد من وجود مسارات إعادة إرسال/تأكيد البريد لتكامل دورة التسجيل.
2. **تغيير كلمة المرور**  
   - Endpoint يطلب `current_password` و`new_password`. يتحقق، يحدّث كلمة المرور، يسجل الحدث، ويرسل إشعارًا للبريد السابق.
3. **تحسين إعدادات اللغة**  
   - تمكين المستخدم من تخصيص اللغة المفضلة (حقل `preferred_language` قائم). ربطها بالميدلوير بحيث تعتمد الردود على إعداد المستخدم وليس فقط header الطلب.

## المرحلة 2 – ميزات الشبكة الاجتماعية
1. **إشعارات داخل التطبيق**  
   - تصميم Router واضح (`/notifications`) لإرجاع الإشعارات غير المقروءة، وضع علامة "تمت القراءة"، وربط الأحداث (تعليق، إعجاب، ذكر) بتوليد إشعار داخلي.  
   - تحديث `NotificationStatus` و`NotificationService` لاستهلاك هذه الواجهة.
2. **قصص/ريلز منتهية الصلاحية**  
   - تفعيل جدول/نموذج Reel، إضافة حقل `expires_at` وتحديث مهام Celery لحذف القصص بعد 24 ساعة.  
   - Endpoint لإنشاء القصة وقراءتها قبل انتهاء المدة.
3. **محادثات جماعية**  
   - توسيع نماذج الرسائل لدعم `group conversations` (جدول أعضاء، دور مسؤول).  
   - تعديل `MessageService`/routers لتمكين إرسال الرسائل داخل المجموعات والتعامل مع الإشعارات المرتبطة.

## المرحلة 3 – الأداء، البحث، والأمان
1. **Redis & caching**  
   - استخدام Redis لتخزين الجلسات النشطة وتخزين مؤقت لاقتراحات البحث/الوسوم. توثيق إعداد Redis في الإنتاج.  
   - التفكير في التقسيم المستقبلي لقواعد البيانات (تعليقات/منشورات) للفصل الأفقي عند الحاجة.
2. **محرك بحث متقدم**  
   - دمج ElasticSearch أو Typesense للحصول على بحث أسرع وأكثر دقة (بما في ذلك دعم suggestions و fuzzy search).  
   - توفير Adapter في `app/modules/search` وتحديث الراوتر لاستخدامه عند تفعيل الخدمة.
3. **OAuth/Awareness**  
   - إكمال تكامل OAuth مع Facebook/Twitter (مسارات `/auth/facebook`, `/auth/twitter`) وإتاحة مشاركة المحتوى عبرهما.  
   - توصية تشغيل واجهة الـAPI خلف WAF (Cloudflare/Azure FrontDoor) لتأمينها، وتشفير الحقول الحساسة (رسائل، إجابات أمنية) في DB.
4. **التدويل والترجمة**  
   - تفعيل `translate_text` فعلياً عند تمرير `translate=true` في `/posts`, `/comments`.  
   - السماح بتحديد اللغة عبر معلمة وتخزينها لكل مستخدم لتوحيد تجربة الواجهة.
5. **لوحة تحكم وتحليلات**  
   - إضافة Endpoint مركزي يعيد أهم الإحصاءات (مستخدمون جدد، أكثر المجتمعات نشاطًا، البلاغات المفتوحة).  
   - تطوير واجهة أو تصدير لـGrafana/Grafite حسب الحاجة.
6. **وثائق وReadme**  
   - إنشاء README.md في الجذر يصف المشروع، كيفية التشغيل، الميزات الأساسية، وروابط الوثائق.  
   - توسيع الوثائق/الويكي بأمثلة استخدام لكل Endpoint مهم لتسهيل عمل الفرق الأمامية.

بعد تنفيذ كل مرحلة من خطة المنتج، يجب إعادة تشغيل `pytest`, `perf_startup`, ومراجعة الأمن (تحقق الأسرار، إعدادات CORS/Hosts، سياسات WAF المقترحة).
