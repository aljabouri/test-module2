"""KonformOS core engine.

Modular-monolith boundaries (Tech Spec v1.0 §2.3):
- core:       cross-cutting primitives (canonical hashing, timeline chain)
- schemas:    Pydantic models enforcing Engineering Rules v1.1 §4 (VAL)
- registry:   Rule-Pack Registry — catalog loading + resolution (System 2)
- evaluation: Compliance Evaluation Engine (System 5)
- api:        FastAPI surface (Tech Spec v1.0 §5)
"""

__version__ = "0.1.0"
