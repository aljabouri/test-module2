# KonformOS — Core Engine (v0.1)

النواة البرمجية الأولى، مستخرَجة **حرفياً** من وثائق `docs/` — كل وحدة تشير لمعرّفات القواعد التي تنفّذها:

| الوحدة | ينفّذ | الوثيقة |
|---|---|---|
| `core/hashing.py` | الختم التشفيري للـTimeline: canonical JSON، سلسلة hash، كشف العبث | INV-TL-02/03/04 |
| `schemas/` | نماذج Pydantic صارمة: Rule, RulePack, ComplianceProfile, RuleMapping | VAL-ID, VAL-RULE-01, VAL-PACK-01, VAL-PROF-01, INV-RP-03, BR-LEG-03 |
| `registry/loader.py` | تحميل كتالوج `docs/rules-catalog` — التحميل هو التحقق (Schema-as-Code) | INV-RP-04/05, §8.1 |
| `registry/resolver.py` | خوارزمية الحسم: latest/pinned، تاريخ السريان، دمج الولايات | §8.7, BR-LEG-04, BR-EVAL-05, EDGE-LEG-02 |
| `evaluation/scoring.py` | معادلة Readiness المرجعية بحذافيرها | BR-EVAL-01..07, INV-RD-01 |
| `scan/static_engine.py` | محرّك فحص HTML داخلي محدد (8 فحوصات بمعرّفات متوافقة مع axe) | §4.4, INV-SC-02 |
| `scan/normalizer.py` | الـNormalizer — قلب الفحص: جدول المطابقة مشتق من الكتالوج، dedup، طابور unmapped | §4.4.3, INV-FD-01, BR-SCAN-03/04 |
| `dossier/sealing.py` | ختم الـDossier + **التحقق العام بلا حساب** (عام بالبناء — بلا هوية) | INV-DS-01/02/03, EDGE-TL-01 |
| `moat/knowledge.py` | Theme Intelligence استباقي + معقّم الخندق (بوابة كتابة واحدة) | INV-KG-01/02, BR-KG-01/02, BR-FP-01/03 |
| `corpus/` | **Golden Corpus**: صفحات مجمّدة بعيوب معلَّمة يدوياً — 100% دقة واستدعاء إلزامية | نقطة خارطة الطريق 7 |
| `api/main.py` | FastAPI: evaluate، scan-html، dossiers، **`/v1/verify/{hash}` العام**، preview | Tech Spec §5, ERR-00 |

## التشغيل

```bash
cd konformos
pip install -e ".[dev]"
pytest                                            # 62 اختباراً تحرس الثوابت والـCorpus
uvicorn --factory konformos.api.main:create_app   # ثم /docs للـOpenAPI
```

## ما بُني وما لم يُبنَ بعد (بترتيب خطة v1.0 §11)

- ✅ قلب المرحلة 0: Registry + Resolution + Evaluation + ختم الإثبات + بذر DE/EU/US.
- ✅ الشريحة الرأسية الكاملة: HTML → محرّك داخلي → Normalizer → Readiness → Dossier مختوم → تحقق عام، + Golden Corpus + Theme Intelligence استباقي.
- ⏭️ التالي: طبقة PostgreSQL (SQLAlchemy + Alembic + trigger منع UPDATE/DELETE على timeline_events + RLS)، ثم axe-core عبر Playwright كمحرّك ثانٍ يُقاس على نفس الـCorpus، ثم Auth/RBAC (§5 من وثيقة القواعد)، ثم Stripe.

كل امتداد يُقاس على معايير القبول AC في `docs/KonformOS_Engineering_Rules_v1.1.md` §9.
