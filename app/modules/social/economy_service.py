from sqlalchemy.orm import Session
from app.modules.posts.models import Post, Reaction
from app.modules.users.models import User
import math


class SocialEconomyService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_quality_score(self, content: str) -> float:
        """
        حساب درجة جودة المحتوى (0-100) بناءً على معايير بسيطة.
        مستقبلاً يمكن استبدال هذا بنموذج AI.
        """
        score = 0.0
        length = len(content)

        # 1. الطول المناسب (ليس قصيراً جداً ولا طويلاً جداً)
        if 50 <= length <= 2000:
            score += 40
        elif length > 2000:
            score += 20  # طويل جداً قد يكون مملاً

        # 2. التنسيق (وجود مسافات وسطور جديدة يدل على ترتيب)
        if "\n" in content:
            score += 10

        # 3. خلوه من التكرار المفرط (مؤشر بسيط)
        words = content.split()
        unique_words = set(words)
        if len(words) > 0:
            diversity_ratio = len(unique_words) / len(words)
            if diversity_ratio > 0.6:  # تنوع لغوي جيد
                score += 30
            elif diversity_ratio > 0.4:
                score += 15

        # 4. بونص إضافي بسيط
        score += 20

        return min(100.0, score)

    def calculate_engagement_score(self, post: Post) -> float:
        """
        حساب درجة التفاعل (0-100) بناءً على اللايكات والتعليقات.
        يستخدم معادلة لوغاريتمية لمنع تضخم الأرقام.
        """
        # وزن التعليق (2) أعلى من اللايك (1)
        # نفترض أن reactions هي علاقة في Post model
        likes_count = (
            self.db.query(Reaction).filter(Reaction.post_id == post.id).count()
        )
        comments_count = len(post.comments)

        raw_score = (likes_count * 1) + (comments_count * 2)

        # تحويل الرقم إلى مقياس 0-100 باستخدام Logarithm
        # log(1) = 0, log(10) = 1, log(100) = 2...
        # نضرب في 20 لنجعل 100 نقطة تفاعل تعادل تقريباً 40-50%
        if raw_score == 0:
            return 0.0

        normalized_score = math.log(raw_score + 1) * 20
        return min(100.0, normalized_score)

    def calculate_originality_score(self, post: Post) -> float:
        """
        حساب درجة الأصالة. إذا كان repost فالأصالة منخفضة.
        """
        if post.is_repost:
            return 10.0  # أصالة منخفضة للمنقول

        # إذا كان لديه "ذكريات مرتبطة" كثيرة منسوخة، تقل الأصالة
        # (هنا نستخدم منطق بسيط: الجديد أصلي افتراضياً ما لم يثبت العكس)
        return 90.0

    def update_post_score(self, post_id: int):
        """
        الدالة الرئيسية: تحسب المجموع الكلي وتحدث المنشور والمستخدم.
        """
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return

        # 1. حساب المكونات
        q_score = self.calculate_quality_score(post.content)
        e_score = self.calculate_engagement_score(post)
        o_score = self.calculate_originality_score(post)

        # 2. تطبيق المعادلة الوزنية
        # Social Credits = (Q * 0.4) + (E * 0.3) + (O * 0.1) + (Feedback * 0.2 - حالياً 0)
        # نعدل الأوزان لتعويض غياب Feedback مؤقتاً: Q=0.5, E=0.4, O=0.1
        total_score = (q_score * 0.5) + (e_score * 0.4) + (o_score * 0.1)

        # 3. تحديث المنشور
        post.quality_score = q_score
        post.originality_score = o_score
        post.score = total_score  # هذا الحقل موجود سابقاً

        # 4. تحديث رصيد المستخدم (Social Credits)
        # نضيف "فرق النقاط" الجديد لرصيد المستخدم، أو نعيد حسابه بالكامل
        # للتبسيط والكفاءة: سنضيف (0.1 * Total Score) لرصيد المستخدم كربح دائم
        user = self.db.query(User).filter(User.id == post.owner_id).first()
        if user:
            # معادلة نمو الرصيد: كل منشور جيد يزيد رصيدك
            credit_earned = total_score * 0.05  # يكسب 5% من نقاط المنشور
            user.social_credits += credit_earned

        self.db.commit()
        return total_score

    # === [ADDITION START] ===
    def check_and_award_badges(self, user_id: int):
        """
        Check if the user qualifies for any new badges based on their stats.
        This should be called after a post is created or a score is updated.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return

        # Get all badges the user doesn't have yet
        existing_badge_ids = [
            b.badge_id
            for b in self.db.query(UserBadge).filter(UserBadge.user_id == user_id).all()
        ]
        potential_badges = (
            self.db.query(Badge).filter(~Badge.id.in_(existing_badge_ids)).all()
        )

        for badge in potential_badges:
            # Check thresholds (Dynamic Logic)
            posts_ok = user.post_count >= badge.required_posts
            score_ok = user.social_credits >= badge.required_score

            if posts_ok and score_ok:
                # Award the badge!
                new_badge = UserBadge(user_id=user.id, badge_id=badge.id)
                self.db.add(new_badge)
                # Notification logic can be added here

        self.db.commit()

    # === [ADDITION END] ===
