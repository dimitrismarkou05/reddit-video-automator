"""Notification creation with best-effort SSE broadcast."""

import asyncio
from typing import Optional

from sqlalchemy.orm import Session

from models import Notification
from api.sse import notification_queue


class NotificationService:
    """Handles notification persistence and optional SSE broadcast."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        notif_type: str,
        level: str,
        message: str,
        details: Optional[dict] = None,
    ) -> Notification:
        """Persist a notification and attempt SSE broadcast (best-effort)."""
        n = Notification(type=notif_type, level=level, message=message, details=details)
        self.db.add(n)
        self.db.commit()

        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(notification_queue.broadcast("notification", {
                    "id": n.id, "type": notif_type, "level": level, "message": message,
                    "details": details, "is_read": False, "created_at": n.created_at.isoformat(),
                }))
        except RuntimeError:
            pass

        return n
