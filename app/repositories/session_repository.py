import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.models.session import UserSession
from app.repositories.base_repository import BaseRepository


class SessionRepository(BaseRepository[UserSession]):
    model = UserSession

    def create(self, session: UserSession) -> UserSession:
        return self.add(session)

    def get_by_refresh_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> UserSession | None:
        stmt = select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def revoke(self, session: UserSession) -> None:
        session.revoked_at = datetime.now(timezone.utc)
        self.db.add(session)
        self.db.flush()

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        self.db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
