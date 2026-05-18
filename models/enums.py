import enum


class UserRole(str, enum.Enum):
    author    = "author"
    buyer     = "buyer"
    manager   = "manager"
    admin     = "admin"
    developer = "developer"


class StartupStatus(str, enum.Enum):
    draft    = "draft"
    active   = "active"
    sold     = "sold"
    archived = "archived"


class DealStatus(str, enum.Enum):
    pending     = "pending"
    active      = "active"
    documents   = "documents"
    closed_ok   = "closed_ok"
    closed_fail = "closed_fail"


class MessageKind(str, enum.Enum):
    text     = "text"
    system   = "system"
    document = "document"


class NotifType(str, enum.Enum):
    deal_new    = "deal_new"
    deal_status = "deal_status"
    message     = "message"
    system      = "system"
    review      = "review"
    ticket      = "ticket"
    payment     = "payment"
    document    = "document"


class ReviewTarget(str, enum.Enum):
    startup = "startup"
    user    = "user"


class TicketStatus(str, enum.Enum):
    open        = "open"
    in_progress = "in_progress"
    closed      = "closed"


class TicketPriority(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


class WithdrawStatus(str, enum.Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"


class PaymentMethod(str, enum.Enum):
    online = "online"
    qr     = "qr"
    cash   = "cash"


class PaymentStatus(str, enum.Enum):
    pending   = "pending"
    confirmed = "confirmed"
    rejected  = "rejected"


# Human-readable Russian labels
DEAL_STATUS_LABELS = {
    DealStatus.pending:     "На рассмотрении",
    DealStatus.active:      "Активна",
    DealStatus.documents:   "Документы",
    DealStatus.closed_ok:   "Закрыта успешно",
    DealStatus.closed_fail: "Закрыта неудачно",
}

STARTUP_STATUS_LABELS = {
    StartupStatus.draft:    "Черновик",
    StartupStatus.active:   "Активен",
    StartupStatus.sold:     "Продан",
    StartupStatus.archived: "В архиве",
}

PAYMENT_METHOD_LABELS = {
    PaymentMethod.online: "Онлайн",
    PaymentMethod.qr:     "По QR-коду",
    PaymentMethod.cash:   "Наличными",
}
