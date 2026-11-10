"""Request identity also carried into explicit conversation and extraction workers."""
from contextlib import contextmanager
from contextvars import ContextVar

ACTOR=ContextVar('highzyme_actor',default=None)
BILLING=ContextVar('highzyme_billing',default={})

@contextmanager
def acting(identity):
    token=ACTOR.set(identity)
    try:yield identity
    finally:ACTOR.reset(token)
