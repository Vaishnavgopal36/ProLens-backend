from datetime import datetime, timezone

from sqlalchemy import select

from app.models.session import UserSession
from app.repositories.base_repository import BaseRepository


class SessionRepository(BaseRepository[UserSession]):
    model = UserSession

    def create(self, session: UserSession) -> UserSession:
        session = self.add(session)
        self.commit()
        return session

    def get_by_refresh_token_hash(self, token_hash: str) -> UserSession | None:
        return self.db.scalar(
            select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        )

    def revoke(self, session: UserSession) -> None:
        session.revoked_at = datetime.now(timezone.utc)
        self.db.add(session)
        self.commit()