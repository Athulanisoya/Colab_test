"""Provision the first administrator without storing a password in a script."""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--district', default='Alappuzha')
    args = parser.parse_args()
    from sqlalchemy import select
    from backend.database.connection import Base, engine, SessionLocal
    from backend.database.models import User
    from backend.schemas import Register
    from backend.utils.security import hash_password
    password = getpass.getpass('New administrator password (at least 10 characters): ')
    if password != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords differ. No account was created.')
    body = Register(name=args.name, email=args.email, password=password, district=args.district)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == body.email)):
            raise SystemExit('An account with this email already exists. No changes were made.')
        db.add(User(name=body.name, email=body.email, district=body.district,
                    role='admin', password_hash=hash_password(body.password)))
        db.commit()
    print('Administrator created. Sign in through the web application.')


if __name__ == '__main__':
    main()
