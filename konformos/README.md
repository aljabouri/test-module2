# KonformOS — Core Engine (v0.1)

النواة البرمجية الأولى، مستخرَجة **حرفياً** من وثائق `docs/` — كل وحدة تشير لمعرّفات القواعد التي تنفّذها:

| الوحدة | ينفّذ | الوثيقة |
|---|---|---|
| `core/hashing.py` | الختم التشفيري للـTimeline: canonical JSON، سلسلة hash، كشف العبث | INV-TL-02/03/04 |
| `schemas/` | نماذج Pydantic صارمة: Rule, RulePack, ComplianceProfile, RuleMapping | VAL-ID, VAL-RULE-01, VAL-PACK-01, VAL-PROF-01, INV-RP-03, BR-LEG-03 |
| `registry/loader.py` | تحميل كتالوج `docs/rules-catalog` — التحميل هو التحقق (Schema-as-Code) | INV-RP-04/05, §8.1 |
| `registry/resolver.py` | خوارزمية الحسم: latest/pinned، تاريخ السريان، دمج الولايات | §8.7, BR-LEG-04, BR-EVAL-05, EDGE-LEG-02 |
| `evaluation/scoring.py` | معادلة Readiness المرجعية بحذافيرها | BR-EVAL-01..07, INV-RD-01 |
| `api/main.py` | FastAPI: health، عرض الحزم، `/v1/evaluate` بغلاف الخطأ الموحّد | Tech Spec §5, ERR-00 |

## التشغيل

```bash
cd konformos
pip install -e ".[dev]"
pytest                                            # 32 اختباراً تحرس الثوابت
uvicorn --factory konformos.api.main:create_app   # ثم /docs للـOpenAPI
```

## ما بُني وما لم يُبنَ بعد (بترتيب خطة v1.0 §11)

- ✅ قلب المرحلة 0: Registry + Resolution + Evaluation + ختم الإثبات + بذر DE/EU/US.
- ⏭️ التالي: طبقة PostgreSQL (SQLAlchemy + Alembic + trigger منع UPDATE/DELETE على timeline_events + RLS)، ثم Scan Engine (Playwright + axe-core → Normalizer)، ثم Auth/RBAC (§5 من وثيقة القواعد)، ثم Stripe.

كل امتداد يُقاس على معايير القبول AC في `docs/KonformOS_Engineering_Rules_v1.1.md` §9.
