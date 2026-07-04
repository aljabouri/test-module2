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
| `scan/axe_engine.py` | **axe-core 4.10.2 عبر Playwright** (مُضمَّن في `vendor/`) — محرّك ثانٍ يمرّ بنفس الـNormalizer ومُثبَّت بلقطة على الـCorpus | §4.4, INV-SC-02 |
| `db/` | **طبقة PostgreSQL**: 19 جدولاً (§6)، trigger يمنع UPDATE/DELETE على الـTimeline، RLS بعزل المنظمات، فهرس "حزمة نشطة واحدة"، مستودعات (Timeline بقفل + بذر idempotent) | INV-TL-01/04, INV-RP-02, INV-ORG-01, INV-KG-01 بنيوياً |
| `migrations/` | Alembic: `0001` المخطط، `0002` تقوية Postgres، `0003` أعمدة تشغيلية + bypass نظامي ضيق | §10.2 |
| `api/security.py` | Argon2id + JWT قصير العمر + حظر الأدوار الحسّاسة بلا MFA | §7.3, VAL-USER-01, RBAC-02 |
| `api/routes_db.py` | **منصة كاملة موصولة بالقاعدة**: auth، properties، ملف الامتثال، fingerprint، فحص غير متزامن (202+poll)، findings بآلة الحالة، fix، Dossier PDF، بوابة القانون (نشر+إعادة حساب)، بوابة الخبير، Stripe webhook | Tech Spec §5 كاملاً |
| `billing/service.py` | مصفوفة Tier×قدرة + SM-SUB قراءة-فقط + webhook idempotent بتوقيع Stripe v1 | BR-BIL, EDGE-BIL-02 |
| `fingerprint/engine.py` | كشف المنصة/الثيم بإشارات مرجّحة + صياغة تحوّطية مدمجة | §4.3, BR-FP-01 |
| `scan/crawler.py` | زاحف Playwright حي: robots.txt، حارس SSRF، أولوية الصفحات الحرجة | BR-SCAN-01/02, VAL-PROP-01 |
| `scan/worker.py` | طابور فحص غير متزامن (SM-SCAN كاملة، اكتمال بمعاملة واحدة) | SM-SCAN-02, INV-SC-01/02 |
| `dossier/pdf.py` | Dossier PDF فعلي مختوم على البايتات + قسم الحدود الإلزامي | INV-DS-01/02/03, BR-CUST-03 |
| `api/dashboard.py` | لوحة تحكم v0 (تسجيل → فحص → Dossier → تحقق) على `/app` | — |
| `api/main.py` | evaluate/scan-html عديمة الحالة + **`/v1/verify/{hash}` العام** (ذاكرة + قاعدة) + preview | ERR-00 |

## التشغيل

```bash
cd konformos
pip install -e ".[dev,db,scan]"
alembic upgrade head                              # يتطلب DATABASE_URL أو Postgres محلياً
pytest                                            # 112 اختباراً (Postgres وaxe يتخطيان تلقائياً إن غابا)
docker compose up                                 # Postgres + API (انظر docker-compose.yml)
uvicorn --factory konformos.api.main:create_app   # ثم /docs للـOpenAPI
```

## ما بُني وما لم يُبنَ بعد (بترتيب خطة v1.0 §11)

- ✅ قلب المرحلة 0: Registry + Resolution + Evaluation + ختم الإثبات + بذر DE/EU/US.
- ✅ الشريحة الرأسية الكاملة: HTML → محرّكان (داخلي + axe) → Normalizer → Readiness → Dossier مختوم → تحقق عام، + Golden Corpus + Theme Intelligence استباقي.
- ✅ طبقة PostgreSQL: المخطط الكامل + التقوية (append-only trigger, RLS, فهرس INV-RP-02) + بذر idempotent — مُختبرة على Postgres 16 حقيقي.
- ✅ المنصة الكاملة (المرحلة 0 وظيفياً): Auth/RBAC + فحص غير متزامن بزاحف حي + بصمة + فوترة بمستويات + Dossier PDF + تحقق عام + بوابتا القانون والخبير + لوحة v0 — اختبار e2e يشغّل القصة كاملة على Postgres وChromium حقيقيين.
- ✅ طبقة النمو: **TOTP MFA فعلي**، **بيان الوصولية** (§ Erklärung)، **Deploy hooks** (Flow C) + **جدولة دورية** + استرداد الطابور بعد إعادة التشغيل، **مقاعد الوكالة** (BR-CUST-04)، **webhooks صادرة موقَّعة HMAC** + سجل إشعارات، **تغذية الخندق الآلية** بعد كل فحص (ببوابات consent/الثقة/التعقيم)، **Adapters جديدة**: Theme/Plugin (zip بحماية zip-bomb)، Design System (عزل بغلاف نظيف)، PDF (علامات PDF/UA عبر pypdf — الربط بالكتالوج كبيانات)، **محوّل Claude API** للإصلاحات (opus-4-8، هبوط رشيق بلا مفتاح)، **TSA backfill** (العمود الوحيد القابل للتعديل بقرار trigger)، **Rate limiting**، وDockerfile/compose/CI.
- ⏭️ المتبقي للإنتاج: Celery/Redis بدل الطابور داخل-العملية (الدلالات نفسها — الاسترداد موجود)، الجلب الدوري لمصادر القانون + semantic diff (البوابة كاملة)، Next.js بدل لوحة v0، Object Storage بدل القرص، ومفاتيح فعلية (Stripe/Anthropic/TSA) + مراجعة الكانزلاي.
- 📌 تباين موثّق بين المحرّكين: axe يقبل placeholder كاسم برمجي للحقل؛ المحرّك الداخلي أصرم عمداً (placeholder ≠ label). القرار: نبقي الأصرم.

كل امتداد يُقاس على معايير القبول AC في `docs/KonformOS_Engineering_Rules_v1.1.md` §9.
