import requests
from bs4 import BeautifulSoup
import validators


def extract_link_preview(url):
    if not validators.url(url):
        return None

    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, "html.parser")

        title = soup.title.string if soup.title else ""
        description = ""
        image = ""

        # محاولة استخراج الوصف
        meta_desc = soup.find("meta", attrs={"name": "description"})
        og_desc = soup.find("meta", property="og:description")
        if meta_desc:
            description = meta_desc["content"]
        elif og_desc:
            description = og_desc["content"]

        # محاولة استخراج الصورة
        og_image = soup.find("meta", property="og:image")
        if og_image:
            image = og_image["content"]

        return {"title": title, "description": description, "image": image, "url": url}
    except Exception as e:
        print(f"Error extracting link preview: {e}")
        return None


# لدي هذه المشروع اريد منك ان تقوم بمراجعته بشكل دقيق جدا جدا وتكون المراجعة شامله تشمل الملفات الرئيسية والفرعية وجميع الميزات ولاخاصيات وكل حرف وكلمه والمهمه الثانيه اعطني تقرير كامل بجميع الميزات والخاصيات والاشياء الموجوده به


# 1. عند تقديم ميزة جديدة لإضافتها للمشروع، قدّم لي إرشادات دقيقة حول كيفية دمجها بشكل صحيح مع جميع الملفات الرئيسية والفرعية.
# 2. تأكد من أن إضافة الميزة الجديدة لا تسبب أي تعارض أو أخطاء في بقية المزايا الموجودة في المشروع.
# 3. تحقق مما إذا كانت الميزة الجديدة موجودة بالفعل؛ إذا كانت كذلك، زودني باقتراحات لتحسينها أو دمجها بشكل أكثر كفاءة.
# 4. في كل مرة أطلب إضافة ميزة جديدة، تأكد من أن المشروع لا يزال يعمل بكفاءة وتوافق تام.
# 5. إذا كان هناك تحسين للميزة المقترحة، قدم لي هذا التحسين لتطبيقه.
# 6. بعد التأكد من نجاح إضافة الميزة، انتقل مباشرةً إلى الميزة التالية بناءً على التعليمات التي سأقدمها.
# مع الرجوع للملفات التي قدمتها:
# 7. عند تقديم الإرشادات والإضافات، اعتمد على الملفات التي قمت بتقديمها سابقًا لضمان التكامل بين الميزة الجديدة والمشروع الحالي.
# 8. إذا كانت الملفات السابقة تحتاج إلى تعديلات لتتناسب مع الميزة الجديدة، قدّم إرشادات محددة حول كيفية تعديلها أو تحديثها لتحقيق التكامل المطلوب.
