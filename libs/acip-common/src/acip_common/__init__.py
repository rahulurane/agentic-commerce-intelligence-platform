"""ACIP shared library.

Shared contracts and utilities imported by every ACIP service (docs/01 §2):
typed config, Pydantic v2 event/domain schemas, the shared feature transforms that
prevent train/serve skew, structured logging, and the confluent-kafka wrapper.
"""

__version__ = "0.1.0"
