"""Seed script to populate test organization, designation, and test users:
- admin@tarento.com (admin)
- employee@tarento.com (employee)
- superadmin@tarento.com (super_admin)
- manager@tarento.com (manager)
All with the same password: "password"
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import OrgStatus, UserRole, UserStatus
from app.models.tenancy import Designation, Organization
from app.models.user import User

engine = create_engine(settings.MIGRATION_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

DEFAULT_PASSWORD = "password"


def seed():
    with SessionLocal() as db:
        # 1. Organization
        org = db.query(Organization).filter(Organization.domain == "tarento.com").first()
        if not org:
            org = Organization(
                name="Tarento",
                domain="tarento.com",
                status=OrgStatus.active,
            )
            db.add(org)
            db.flush()
            print(f"Created Organization: {org.name} ({org.domain}) -> id: {org.id}")
        else:
            print(f"Found existing Organization: {org.name} -> id: {org.id}")

        # 2. Designation
        desig = (
            db.query(Designation)
            .filter(Designation.organization_id == org.id, Designation.name == "Software Engineer")
            .first()
        )
        if not desig:
            desig = Designation(
                organization_id=org.id,
                name="Software Engineer",
            )
            db.add(desig)
            db.flush()
            print(f"Created Designation: {desig.name} -> id: {desig.id}")
        else:
            print(f"Found existing Designation: {desig.name} -> id: {desig.id}")

        # 3. Users definition
        users_data = [
            {
                "email": "admin@tarento.com",
                "role": UserRole.admin,
                "first_name": "Admin",
                "last_name": "Tarento",
                "organization_id": org.id,
                "designation_id": None,
            },
            {
                "email": "employee@tarento.com",
                "role": UserRole.employee,
                "first_name": "Employee",
                "last_name": "Tarento",
                "organization_id": org.id,
                "designation_id": desig.id,
            },
            {
                "email": "superadmin@tarento.com",
                "role": UserRole.super_admin,
                "first_name": "Superadmin",
                "last_name": "Tarento",
                "organization_id": org.id,
                "designation_id": None,
            },
            {
                "email": "manager@tarento.com",
                "role": UserRole.manager,
                "first_name": "Manager",
                "last_name": "Tarento",
                "organization_id": org.id,
                "designation_id": None,
            },
        ]

        hashed_pw = hash_password(DEFAULT_PASSWORD)

        for u_data in users_data:
            existing = db.query(User).filter(User.email == u_data["email"]).first()
            if existing:
                existing.first_name = u_data["first_name"]
                existing.last_name = u_data["last_name"]
                existing.role = u_data["role"]
                existing.organization_id = u_data["organization_id"]
                existing.designation_id = u_data["designation_id"]
                existing.password_hash = hashed_pw
                existing.status = UserStatus.active
                print(f"Updated user: {existing.email} (role: {existing.role.value})")
            else:
                user = User(
                    email=u_data["email"],
                    first_name=u_data["first_name"],
                    last_name=u_data["last_name"],
                    role=u_data["role"],
                    organization_id=u_data["organization_id"],
                    designation_id=u_data["designation_id"],
                    password_hash=hashed_pw,
                    status=UserStatus.active,
                )
                db.add(user)
                print(f"Created user: {user.email} (role: {user.role.value})")

        db.commit()
        print("\nAll 4 test users successfully seeded with password:", DEFAULT_PASSWORD)


if __name__ == "__main__":
    seed()
