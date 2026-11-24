import hashlib
import json
from ..database import _json_default
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func
from ..models import WriteSubmission, ExternalReceipt, Payment, CarWashTransaction


def begin_submission(db, user, key, operation, payload):
    if key is None:
        return None, None  # Compatibility for older clients; new clients supply a key.
    fingerprint = hashlib.sha256(json.dumps({'operation': operation, 'payload': payload}, sort_keys=True, default=_json_default).encode()).hexdigest()
    previous = db.scalar(select(WriteSubmission).where(WriteSubmission.user_id == user.id, WriteSubmission.key == key))
    if previous:
        if previous.fingerprint != fingerprint:
            raise HTTPException(409, 'This submission key was already used for a different request.')
        return previous, previous.response
    entry = WriteSubmission(user_id=user.id, key=key, fingerprint=fingerprint)
    db.add(entry)
    db.flush()
    return entry, None


def finish_submission(entry, response):
    if entry is not None:
        entry.response = jsonable_encoder(response)


def reserve_receipt(db, reference, source, source_id):
    if not reference or not reference.strip():
        raise HTTPException(400, 'Enter the external receipt reference.')
    reference = reference.strip().upper()
    if len(reference) > 100:
        raise HTTPException(422, 'Receipt reference must be at most 100 characters.')
    # Include legacy records, which predate the shared reservation table.
    old_payment = db.scalar(select(Payment.id).where(Payment.method == 'm-pesa', Payment.status != 'rejected',
                            func.upper(func.trim(Payment.reference)) == reference, Payment.id != (source_id if source == 'payment' else -1)))
    old_wash = db.scalar(select(CarWashTransaction.id).where(CarWashTransaction.payment_method == 'm-pesa',
                         func.upper(func.trim(CarWashTransaction.mpesa_reference)) == reference,
                         CarWashTransaction.id != (source_id if source == 'carwash' else -1)))
    if old_payment or old_wash or db.get(ExternalReceipt, reference):
        raise HTTPException(409, 'This receipt reference is already recorded.')
    db.add(ExternalReceipt(reference=reference, source=source, source_id=source_id))
    db.flush()  # Database uniqueness also protects concurrent restaurant/wash submissions.
    return reference
