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
