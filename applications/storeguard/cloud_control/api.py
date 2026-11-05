"""Authenticated Cloud Run command service for deterministic DR rehearsals.

Deploy private with ONLY the executive service account as run.invoker.
Service-to-service IAM, not an untrusted request header, authenticates callers.
Commands below MUST NOT be advertised as human approval or live recovery.
"""
from __future__ import annotations
import os
import re
from fastapi import FastAPI, HTTPException
from google.cloud import firestore
from google.api_core.exceptions import Conflict
from pydantic import BaseModel, Field
from .core import PHASES, ACTIONS, new_exercise, transition, TransitionDenied

app = FastAPI(title='StoreGuard DR Simulation Control', docs_url=None, redoc_url=None, openapi_url=None)
COLLECTION = 'storeguard_control_exercises'
ID_PATTERN = re.compile(r'^[a-f0-9]{32}$')

def db():
    project = os.environ['GOOGLE_CLOUD_PROJECT']
    database = os.environ['STOREGUARD_EVIDENCE_DATABASE']
    if database == '(default)':
        raise RuntimeError('Refusing operational database')
    return firestore.Client(project=project, database=database)

class Command(BaseModel):
    action: str = Field(max_length=32)
    expected_version: int = Field(ge=0, le=100)

@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'simulation-only'}

@app.post('/exercises', status_code=201)
def create_exercise():
    record = new_exercise()
    db().collection(COLLECTION).document(record['id']).create(record)
    return record

@app.get('/exercises/{exercise_id}')
def get_exercise(exercise_id: str):
    if not ID_PATTERN.fullmatch(exercise_id):
        raise HTTPException(400, 'Invalid exercise ID')
    doc = db().collection(COLLECTION).document(exercise_id).get()
    if not doc.exists:
        raise HTTPException(404, 'Exercise not found')
    return doc.to_dict()

@app.post('/exercises/{exercise_id}/commands')
def apply(exercise_id: str, command: Command):
    if not ID_PATTERN.fullmatch(exercise_id):
        raise HTTPException(400, 'Invalid exercise ID')
    if command.action not in ACTIONS:
        raise HTTPException(400, 'Unknown command')
    ref = db().collection(COLLECTION).document(exercise_id)
    transaction = ref._client.transaction()

    @firestore.transactional
    def mutate(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise HTTPException(404, 'Exercise not found')
        current = snap.to_dict()
        if current['version'] != command.expected_version:
            raise HTTPException(409, 'Stale exercise version; refresh first')
        try:
            updated = transition(current, command.action, 'executive-service-identity')
        except TransitionDenied as e:
            raise HTTPException(409, str(e)) from e
        tx.set(ref, updated)
        return updated
    return mutate(transaction)
