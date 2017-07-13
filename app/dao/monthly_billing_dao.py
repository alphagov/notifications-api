from app import db


def update_monthly_billing(monthly_billing):
    db.session.add(monthly_billing)
    db.session.commit()
