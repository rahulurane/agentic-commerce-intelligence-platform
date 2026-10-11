"""ACIP graph-projector: the always-on read-model + graph projector (docs/03 §3-4).

Consumes ``txn.lifecycle`` + ``agent.verdicts`` + ``decision.log`` on one Kafka consumer
(group ``graph-projector``) and projects each event into both the Neo4j transaction graph
(docs/03 §3) and the Postgres read models (docs/03 §4). Projections are idempotent
(Postgres ``ON CONFLICT`` upserts keyed by primary key / ``event_id``, Neo4j ``MERGE``
keyed by id) and the consumer commits only AFTER a successful project, so replays dedupe
rather than duplicate (docs/01 §6). It OWNS runtime read-model population — it calls
``acip_common.bootstrap.ensure_read_model_schema`` on startup (the always-on side of fix
A.1) so a fresh stack with no seed still has the tables.
"""

from __future__ import annotations

__all__: list[str] = []
