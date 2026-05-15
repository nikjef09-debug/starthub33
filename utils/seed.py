import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password
from models.enums import (
    UserRole, StartupStatus, DealStatus,
    MessageKind, NotifType, TicketPriority, WithdrawStatus,
)
from models.user import User, Wallet, Transaction, ActivityLog
from models.startup import Tag, Startup
from models.deal import Deal, Message
from models.support import SupportTicket, Notification, NewsPost, Review
from utils.helpers import slugify


async def seed_db(db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == "admin@starthub.ru"))
    if result.scalar_one_or_none():
        return  # already seeded

    # ── Users ──────────────────────────────────────────────────────────────────
    admin = User(
        email="admin@starthub.ru", username="admin",
        hashed_password=hash_password("admin123"), role=UserRole.admin,
        full_name="Главный Администратор", is_active=True, is_verified=True,
        bio="Администратор платформы StartHub", location="Москва",
    )
    author = User(
        email="author@starthub.ru", username="neuralflow",
        hashed_password=hash_password("author123"), role=UserRole.author,
        full_name="Михаил Романов", is_active=True, is_verified=True,
        bio="Серийный предприниматель, 3 экзита.", location="Санкт-Петербург",
        telegram="@mromanov",
    )
    buyer = User(
        email="buyer@starthub.ru", username="investor_dm",
        hashed_password=hash_password("buyer123"), role=UserRole.buyer,
        full_name="Дмитрий Козлов", is_active=True, is_verified=True,
        bio="Angel investor, 50+ портфельных компаний.", location="Москва",
        telegram="@dkozlov",
    )
    manager = User(
        email="manager@starthub.ru", username="manager_kate",
        hashed_password=hash_password("manager123"), role=UserRole.manager,
        full_name="Екатерина Смирнова", is_active=True, is_verified=True,
        bio="Менеджер сделок, 5 лет опыта в M&A", location="Москва",
    )
    db.add_all([admin, author, buyer, manager])
    await db.flush()

    # ── Wallets ────────────────────────────────────────────────────────────────
    for u in [admin, author, buyer, manager]:
        db.add(Wallet(user_id=u.id, balance=0.0))
    await db.flush()

    # ── Tags ───────────────────────────────────────────────────────────────────
    tag_names = ["AI", "FinTech", "GreenTech", "B2B", "SaaS", "Blockchain", "Mobile", "EdTech"]
    tags = []
    for t in tag_names:
        tag = Tag(name=t, slug=slugify(t))
        db.add(tag)
        tags.append(tag)
    await db.flush()

    # ── Startups ───────────────────────────────────────────────────────────────
    startups_data = [
        dict(title="NeuralFlow — автоматизация документов", category="AI / ML", stage="Series A",
             tagline="ИИ для юридических документов", emoji="🤖",
             description="Платформа автоматического заполнения и анализа юридических документов на базе LLM. Экономит до 80% времени юристов. 200+ корпоративных клиентов.",
             price=12_000_000, revenue=3_500_000, valuation=60_000_000, team_size=12, founded_year=2022,
             is_featured=True, status=StartupStatus.active),
        dict(title="EcoChain — углеродные токены", category="GreenTech", stage="Seed",
             tagline="Блокчейн для экологии", emoji="🌱",
             description="Блокчейн-решение для верификации и торговли углеродными кредитами. Партнёры: 12 корпораций из Fortune 500.",
             price=8_000_000, revenue=1_200_000, valuation=25_000_000, team_size=6, founded_year=2023,
             status=StartupStatus.active),
        dict(title="MedSync — телемедицина B2B", category="HealthTech", stage="Series B",
             tagline="Корпоративная телемедицина", emoji="💊",
             description="Платформа корпоративной телемедицины с интеграцией в HR-системы. 40+ корпоративных клиентов, NPS 72.",
             price=25_000_000, revenue=8_000_000, valuation=120_000_000, team_size=35, founded_year=2021,
             is_featured=True, status=StartupStatus.active),
        dict(title="FinPilot — AI финансовый советник", category="FinTech", stage="Pre-seed",
             tagline="Персональный CFO для МСБ", emoji="📊",
             description="ИИ-платформа финансового планирования для малого бизнеса. Beta: 500 компаний, churn 3%.",
             price=5_000_000, revenue=500_000, valuation=15_000_000, team_size=4, founded_year=2024,
             status=StartupStatus.active),
        dict(title="LogiBot — роботизация склада", category="Logistics", stage="Seed",
             tagline="Автономные складские роботы", emoji="🤖",
             description="Система управления автономными роботами для складской логистики. ROI клиентов: 180%. 3 пилота.",
             price=15_000_000, revenue=4_000_000, valuation=45_000_000, team_size=18, founded_year=2022,
             status=StartupStatus.active),
        dict(title="EduSpace — EdTech платформа", category="EdTech", stage="Series A",
             tagline="Адаптивное обучение 2.0", emoji="📚",
             description="Персонализированная платформа онлайн-обучения с адаптивными траекториями. 50k+ студентов, retention 68%.",
             price=18_000_000, revenue=6_000_000, valuation=80_000_000, team_size=22, founded_year=2021,
             status=StartupStatus.active),
    ]
    created_startups = []
    for s_data in startups_data:
        slug = slugify(s_data["title"]) + f"-{uuid.uuid4().hex[:6]}"
        startup = Startup(author_id=author.id, slug=slug, **s_data)
        db.add(startup)
        created_startups.append(startup)
    await db.flush()

    # ── Sample deal ────────────────────────────────────────────────────────────
    deal = Deal(
        startup_id=created_startups[0].id, buyer_id=buyer.id,
        status=DealStatus.active, amount=10_000_000,
        note="Заинтересован в серьёзных переговорах по NeuralFlow",
    )
    db.add(deal)
    await db.flush()

    db.add(Message(
        deal_id=deal.id, sender_id=None, type=MessageKind.system,
        body="Сделка создана. Покупатель: Дмитрий Козлов. Ожидаем подтверждения автора.",
    ))

    # ── Sample reviews ─────────────────────────────────────────────────────────
    from models.enums import ReviewTarget
    reviews_data = [
        dict(rating=5, comment="Отличный стартап, команда профессионалов. Всё прозрачно."),
        dict(rating=4, comment="Хорошая идея, есть вопросы по юнит-экономике. В целом позитивно."),
        dict(rating=5, comment="Быстро вышли на контакт, документы в порядке. Рекомендую."),
    ]
    for rd in reviews_data:
        db.add(Review(
            author_id=buyer.id,
            target=ReviewTarget.startup,
            startup_id=created_startups[0].id,
            **rd,
        ))

    # ── Support ticket ─────────────────────────────────────────────────────────
    db.add(SupportTicket(
        user_id=buyer.id,
        subject="Как загрузить документы в сделку?",
        body="Не могу найти кнопку загрузки документов в интерфейсе чата сделки.",
        priority=TicketPriority.medium,
    ))

    # ── Notification ───────────────────────────────────────────────────────────
    db.add(Notification(
        user_id=author.id, type=NotifType.deal_new,
        title="Новая сделка по NeuralFlow",
        body="Инвестор Дмитрий Козлов предложил ₽10 млн",
        link=f"/deal/{deal.id}",
    ))

    # ── News & Blog posts ──────────────────────────────────────────────────────
    news_posts = [
        NewsPost(
            author_id=admin.id, title="StartHub запустил новую версию платформы",
            slug="starthub-v2-launch", is_published=True, is_blog=False,
            excerpt="Мы выпустили масштабное обновление с новым интерфейсом чата и системой документооборота.",
            body="Команда StartHub рада представить версию 2.0 платформы. Новый чат в режиме реального времени, полноценный документооборот и умная система нотификаций делают процесс сделки прозрачным и быстрым.",
        ),
        NewsPost(
            author_id=admin.id, title="Рынок M&A стартапов: итоги 2024 года",
            slug="ma-market-2024-results", is_published=True, is_blog=False,
            excerpt="Объём сделок по купле-продаже стартапов вырос на 34% по сравнению с 2023 годом.",
            body="По данным аналитиков, рынок слияний и поглощений стартапов показал рекордный рост. Наиболее активными были сегменты AI/ML и FinTech. StartHub зафиксировал рост числа сделок на 67%.",
        ),
        NewsPost(
            author_id=admin.id, title="Как привлечь инвестора за 30 дней",
            slug="how-to-get-investor-30-days", is_published=True, is_blog=True,
            excerpt="Делимся проверенными стратегиями и реальными кейсами наших пользователей.",
            body="Привлечение инвестиций — это процесс, а не событие. Ключевые элементы: чёткий питч-дек, актуальная финансовая модель и правильная целевая аудитория инвесторов. Рассказываем как это работает на практике.",
        ),
        NewsPost(
            author_id=admin.id, title="5 ошибок при продаже стартапа",
            slug="5-mistakes-selling-startup", is_published=True, is_blog=True,
            excerpt="Разбираем типичные ошибки, которые тормозят сделку или снижают оценку.",
            body="На основе 200+ сделок, закрытых на платформе, мы выделили пять самых частых ошибок: завышенная оценка без обоснования, неготовность к due diligence, отсутствие финансовой модели, слабый питч и долгие ответы на запросы.",
        ),
    ]
    db.add_all(news_posts)

    # ── Activity log ───────────────────────────────────────────────────────────
    db.add(ActivityLog(
        user_id=admin.id, action="platform_launch",
        entity="system", detail="StartHub v2 launched",
    ))

    await db.commit()
