# كتالوج القواعد — Rules-as-Data Seed

المحتوى الفعلي الذي سيُبذَر في **Rule-Pack Registry** (النظام 2) عند البرمجة. يجسّد مبدأ P2 (Rules-as-Data): المعايير بيانات مُصدَّرة محكومة بـSchema صارم، لا كود.

## البنية

```
rules-catalog/
├── schemas/                      # البنية (Schema-as-Code) — v1.0 §8.1
│   ├── rule.schema.json          # المعيار الذرّي
│   ├── rule-pack.schema.json     # الحزمة المُصدَّرة (يفرض INV-RP-03 شرطياً)
│   ├── rule-mapping.schema.json  # التكافؤات عبر الأطر
│   └── compliance-profile.schema.json
└── seed/                         # المحتوى (Rules-as-Data)
    ├── rules.wcag22.json         # 55 معياراً: WCAG 2.2 كاملة A (31) + AA (24)
    ├── rule-packs/
    │   ├── DE-2026.1.json        # BFSG/BITV → EN 301 549 → WCAG 2.1 AA (49 قاعدة)
    │   ├── EU-2026.1.json        # EAA → EN 301 549 → WCAG 2.1 AA (49 قاعدة)
    │   └── US-2026.1.json        # ADA Title II + 508 → WCAG 2.1 AA (49 قاعدة)
    └── rule-mappings.json        # WCAG ↔ EN 301 549 ↔ BFSG ↔ ADA/508 (55 تكافؤاً)
```

## قرارات مضمَّنة (اقرأ قبل الاستخدام)

1. **الترميز موحّد على WCAG 2.2** (`wcag-2.2-x.y.z`) حتى للحزم المبنية قانونياً على WCAG 2.1 — المعايير المشتركة متطابقة المحتوى، وهذا يمنع ازدواج الكيانات عند ترقية EN 301 549 (سيناريو v1.0 §8.6).
2. **الحزم الثلاث تستثني قواعد 2.2 الست الجديدة** (2.4.11, 2.5.7, 2.5.8, 3.2.6, 3.3.7, 3.3.8) لأن الأطر السارية (EN 301 549 V3.2.1، قاعدة ADA 2024) تشير إلى WCAG 2.1. القواعد الست **موجودة في الكتالوج** جاهزة لحزم `-2026.2` — هذا هو اختبار Rules-as-Data الحاسم: الترقية = حزمة جديدة، صفر كود.
3. **كل الحزم `status: draft` و`signed_by: null`** — مبدأ P3: لا نشر بلا توقيع Legal Curator بشري. البذر ليس استثناءً (BR-LEG-03: `seed: true` + `seed_provenance`).
4. **الترجيحات (weights) تقدير هندسي أولي** مبرَّر في `seed_provenance` — تصبح معتمدة فقط بالتوقيع. لاحظ اختلافها بين DE وUS لنفس القاعدة (مثل 1.1.1: وزن 9 في DE و10 في US بحكم أنماط التقاضي) — هذا مقصود (v1.0 §8.3).
5. **`automatable` صادقة**: 23/55 آلية (42%) عبر axe-core مع `manual_fallback` حيث التغطية جزئية؛ 32 يدوية بـ`expert_guidance`. لا مبالغة في الأتمتة (BR-EVAL-04 تعتمد على هذا الصدق).
6. **معيار 4.1.1 Parsing غائب عمداً** — محذوف في WCAG 2.2.

## كيف يُبذَر لاحقاً

```
seed script (المرحلة 0):
1. حمّل rules.wcag22.json → صفوف جدول rules (validate ضد rule.schema.json)
2. حمّل rule-mappings.json → جدول rule_mappings
3. حمّل rule-packs/*.json → جدول rule_packs بحالة draft
4. الـLegal Curator يراجع في البوابة → يوقّع → draft → active (SM-RP)
```

التحقق الآلي (schema + اتساق مرجعي + أعداد WCAG الرسمية) موصوف في وثيقة القواعد v1.1 §9 (AC المرحلة 0).
