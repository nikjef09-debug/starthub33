# Import all models so SQLAlchemy registers them before create_all()
from models.user import User, PasswordResetToken, Wallet, Transaction, ActivityLog  # noqa
from models.startup import Tag, Startup  # noqa
from models.deal import Deal, Message, DealDocument, Payment  # noqa
from models.support import (  # noqa
    Notification, Review, SupportTicket, NewsPost,
    PlatformSetting, CustomRole, EmailCampaign, RoleConfig,
    EmailVerificationToken,
)
from models.subscription import Subscription  # noqa
