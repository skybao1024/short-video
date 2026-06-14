#!/usr/bin/env python
"""Create the first client user account for a fresh installation."""

import argparse
import asyncio
import getpass
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.session import async_session
from app.models.user import User
from app.schemas.client.auth import validate_password_strength


class BootstrapError(Exception):
    """Raised when first-user bootstrap cannot continue."""


def parse_args() -> argparse.Namespace:
    """Parse bootstrap command arguments."""
    parser = argparse.ArgumentParser(
        description="Create the first active, verified client user."
    )
    parser.add_argument(
        "--email",
        default=os.getenv("BOOTSTRAP_USER_EMAIL"),
        help="User email. Defaults to BOOTSTRAP_USER_EMAIL.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("BOOTSTRAP_USER_PASSWORD"),
        help="User password. Defaults to BOOTSTRAP_USER_PASSWORD.",
    )
    parser.add_argument(
        "--first-name",
        default=os.getenv("BOOTSTRAP_USER_FIRST_NAME"),
        help="Optional first name. Defaults to BOOTSTRAP_USER_FIRST_NAME.",
    )
    parser.add_argument(
        "--last-name",
        default=os.getenv("BOOTSTRAP_USER_LAST_NAME"),
        help="Optional last name. Defaults to BOOTSTRAP_USER_LAST_NAME.",
    )
    parser.add_argument(
        "--prompt-password",
        action="store_true",
        help="Prompt for the password instead of reading command arguments.",
    )
    return parser.parse_args()


def get_bootstrap_password(args: argparse.Namespace) -> str:
    """Resolve the bootstrap password without logging it."""
    if args.prompt_password:
        password = getpass.getpass("Password: ")
        confirm_password = getpass.getpass("Confirm password: ")
        if password != confirm_password:
            raise BootstrapError("Passwords do not match.")
        return password

    if args.password:
        return args.password

    raise BootstrapError(
        "Password is required. Set BOOTSTRAP_USER_PASSWORD or use --prompt-password."
    )


async def create_first_user(
    email: str, password: str, first_name: str | None, last_name: str | None
) -> User:
    """Create the first user if the user table is empty."""
    async with async_session() as db:
        existing_count = await db.scalar(select(func.count(User.id)))
        if existing_count:
            raise BootstrapError(
                "A client user already exists. First-user bootstrap was skipped."
            )

        existing_user = await db.scalar(select(User).where(User.email == email))
        if existing_user:
            raise BootstrapError("A user with this email already exists.")

        user = User(
            email=email,
            hashed_password=User.get_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_verified=True,
            auth_provider="email",
            last_active_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def main() -> int:
    """Run the first-user bootstrap flow."""
    args = parse_args()
    email = (args.email or "").strip().lower()
    if not email:
        raise BootstrapError("Email is required. Set BOOTSTRAP_USER_EMAIL.")

    password = get_bootstrap_password(args)
    validate_password_strength(password)

    user = await create_first_user(
        email=email,
        password=password,
        first_name=args.first_name,
        last_name=args.last_name,
    )
    print(f"Created first client user: id={user.id}, email={user.email}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except BootstrapError as exc:
        print(f"Bootstrap skipped: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except ValueError as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
