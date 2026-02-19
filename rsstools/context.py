"""Context variables for request tracing"""

from contextvars import ContextVar
from uuid import uuid4

correlation_id: ContextVar[str] = ContextVar('correlation_id', default='')


def set_correlation_id(cid: str = '') -> str:
    if not cid:
        cid = uuid4().hex[:12]
    correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    return correlation_id.get('')
