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


# الان هذه التعليمات  الاساسية :بنائا على جميع الملفات ساعطيك بعض الاضافات التي اريد اضافتها للمشروع سابدا باضافة تلوى الاخرى في كل مره اريدك ان ترشدني بشكل دقيق كيف ان اقوم باضافتها بشكل صحيح وجعلها تعلم بتوافق مع جميع الملفات الرئيسيية والفرعية اريد ان يكون المشروع متوافق ويعمل باحسن درجة دون التاثير او احداث خطا في باقي الميزات وعند الانتهاء ننتقل للميزه الاخرى لكن في كل مره اريدك ان تلتزم فيما قلته لك الان وفي حال كان هناك اي تحسين في الميزه اعطني التحسين
