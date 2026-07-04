# KonformOS — وثيقة المواصفات التقنية والمعمارية
## Technical Specification & System Design (SRS)
### الإصدار 1.0 · يوليو 2026

---

## ضبط الوثيقة (Document Control)

| الحقل | القيمة |
|---|---|
| اسم المنتج | KonformOS — Accessibility Compliance Infrastructure |
| نوع الوثيقة | System Design / Technical Specification (معمارية، بلا كود تطبيقي) |
| الجمهور | مهندسو Backend/Frontend/Data، مطوّرو المستقبل، شركاء تقنيون |
| المصدر الاستراتيجي | `KonformOS_Strategy_Journey.md` (الأصل الاستراتيجي — هذه الوثيقة تُنفّذه) |
| المكدّس المعتمد | Python/FastAPI · PostgreSQL · Next.js/TypeScript · Node.js (مهام حيّة) |
| قرار التخزين القانوني | JSONB مُهيكَل بإصدار في DB + JSON Schema/Pydantic صارم في الكود |
| قرار الأتمتة | Legal Watcher نصف-آلي (خبير يراجع) أول سنة |

> **تنبيه:** هذه وثيقة هندسية للتخطيط. القرارات القانونية (بنية المسؤولية، الختم الزمني، UPL، التجهيل تحت DSGVO) يجب مراجعتها مع كانزلاي مختص قبل الإنتاج.

---

## الفهرس

1. [نظرة عامة ونطاق النظام](#1)
2. [المعمارية عالية المستوى](#2)
3. [نماذج البيانات الأساسية](#3)
4. [مواصفة الأنظمة الفرعية العشرة](#4)
5. [تصميم الـAPI الخارجي](#5)
6. [مخطط قاعدة البيانات](#6)
7. [الأمن والخصوصية (DSGVO)](#7)
8. [الطبقة القانونية — Compliance Profile Schema (القلب)](#8)
9. [تدفّقات المستخدم الرئيسية](#9)
10. [المكدّس التقني والبنية التحتية](#10)
11. [خطة البناء المرحلية](#11)

---

<a name="1"></a>
# 1. نظرة عامة ونطاق النظام

## 1.1 ما هو KonformOS تقنياً

KonformOS **بنية تحتية للامتثال الرقمي (Compliance Infrastructure)**، لا ماسح مواقع. جوهرها **Router بمحورين** يوجّه كل فحص:

- **المحور التقني:** ما هو Stack المتجر؟ (Fingerprint)
- **المحور القانوني:** أي معايير تنطبق؟ (Compliance Profile — يختاره العميل: 🇩🇪/🇪🇺/🇺🇸 أو دمج)

الناتج: **Readiness Score** موثَّق زمنياً بختم تشفيري، قابل للتقديم للجهات الرقابية كـ**إثبات اجتهاد (Nachweis der Bemühungen)**.

## 1.2 المبادئ المعمارية الحاكمة (Design Principles)

هذه المبادئ تحكم كل قرار في الوثيقة؛ أي خرق لها علامة خطأ تصميمي:

| # | المبدأ | التطبيق |
|---|---|---|
| P1 | **Normalize-then-Process** | كل مدخل (URL/Theme/Plugin/PDF) يُطبَّع إلى `Finding` موحّد قبل التقييم. مدخل جديد = Adapter، لا نظام. |
| P2 | **Rules-as-Data** | المعايير بيانات مُصدَّرة (Versioned JSONB)، لا كود. تحديث قانون = صف جديد، لا Deploy. |
| P3 | **Human-Signed Legal Changes** | لا تغيير قانوني يُطبَّق آلياً. LLM يقترح، خبير/Prüfstelle يوقّع. |
| P4 | **Append-Only Evidence** | الـTimeline سجل إلحاقي مختوم تسلسلياً (Hash-Chain). لا حذف، لا تعديل بأثر رجعي. |
| P5 | **Privacy by Design** | التجهيل والموافقة (Consent) في التصميم، لا إضافة لاحقة. بيانات العملاء تحت DSGVO. |
| P6 | **Versioned Everything** | القواعد، الملفات القانونية، الـFingerprints، الـDossiers — كلها مُصنَّفة بإصدار وتاريخ. |
| P7 | **Zero Marginal Diagnosis** | المعرفة تُبنى مرة (Theme/Rule) وتُطبَّق ملايين المرات. الخندق يقلّل تكلفة كل فحص جديد. |

## 1.3 داخل النطاق / خارجه (Scope)

**داخل النطاق (v1):** Legal Ingestion نصف-آلي · Fingerprint · فحص متعدد المدخلات · تقييم امتثال متعدد الولايات · شرح وإصلاح AI · Knowledge Graph أساسي · إدارة عميل + Timeline مختوم + Dossier · Stripe · طابور مراجعة Prüfstelle.

**خارج النطاق (مؤجّل ببوابات):** GitHub Action/CI · وكيل PR مستقل · White-Label كامل · تطبيق موبايل · أتمتة Legal Watcher الكاملة · حِزم دول أوروبية فردية تتجاوز EAA العام · Auto-PR للإصلاحات.

## 1.4 المستخدمون (Actors)

| Actor | الوصف | الصلاحيات الجوهرية |
|---|---|---|
| **Merchant** | تاجر SMB يملك متجراً/متاجر | فحص، عرض Readiness، توليد Dossier، اشتراك |
| **Agency** | وكالة تدير متاجر عملاء متعددين | كل ما سبق × مقاعد متعددة (White-Label لاحقاً) |
| **Expert Reviewer** | مدقق BITV-Test معتمد (Prüfstelle) | مراجعة Findings يدوياً، توقيع التحقق، مراجعة تغييرات القانون |
| **Legal Curator** | خبير داخلي يراجع تنبيهات القانون | تصديق تحديثات Rule-Pack من طابور المراجعة |
| **System (Automated)** | مهام مجدولة | Watcher، إعادة حساب Readiness، تنبيهات |
| **Admin** | فريق KonformOS | إدارة كل شيء، مراقبة الصحة |

---

<a name="2"></a>
# 2. المعمارية عالية المستوى

## 2.1 الأنظمة الفرعية العشرة

```
┌─────────────────────────────────────────────────────────────────────┐
│                        KonformOS Platform                            │
│                                                                      │
│  ┌────────────────────┐         ┌─────────────────────────────┐     │
│  │ 1. Legal Ingestion │────────▶│ 2. Rule-Pack Registry       │     │
│  │    Engine          │ يُصدِر   │    (Versioned JSONB)         │     │
│  │ (مصادر رسمية →     │  حزمة   │                             │     │
│  │  Semantic Diff →   │         └──────────────┬──────────────┘     │
│  │  LLM → توقيع خبير) │                        │                    │
│  └────────────────────┘                        │ يغذّي القواعد       │
│                                                 ▼                    │
│  ┌────────────────────┐   Stack   ┌─────────────────────────────┐   │
│  │ 3. Fingerprint     │──────────▶│ 5. Compliance Evaluation    │   │
│  │    Engine          │           │    Engine                   │   │
│  └────────────────────┘           │ (Findings + Profile + Pack  │   │
│           ▲                        │  → Readiness لكل ولاية)     │   │
│           │ Stack                  └──────────────┬──────────────┘   │
│  ┌────────┴───────────┐   Findings                │ Readiness        │
│  │ 4. Multi-Input     │──────────────────────────▶│                  │
│  │    Scan Engine     │  (URL/Theme/Plugin/       ▼                  │
│  │  [Adapters]        │   Design System/PDF)  ┌─────────────────┐   │
│  └────────┬───────────┘                        │ 6. AI Fix &     │   │
│           │ كل فحص                              │    Explanation  │   │
│           ▼                                     └────────┬────────┘   │
│  ┌────────────────────┐                                  │           │
│  │ 7. Knowledge Graph │◀── يغذّي ──────────────────────────┘           │
│  │    & Data Moat     │  (Fingerprints + أخطاء + إصلاحات صامدة)      │
│  │ (تدريب AI + خبير)  │                                              │
│  └────────────────────┘                                              │
│                                                                      │
│  ┌────────────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │ 8. Customer &      │   │ 9. Billing & │   │ 10. Integration  │   │
│  │    Dossier Mgmt    │   │    Access    │   │  & Notification  │   │
│  │ (Timeline مختوم +  │   │  (Stripe)    │   │ (Changelog +     │   │
│  │  Audit Dossier)    │   │              │   │  Prüfstelle Portal)│  │
│  └────────────────────┘   └──────────────┘   └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## 2.2 مسؤولية كل نظام (Bounded Contexts)

| # | النظام | المسؤولية الوحيدة | يعتمد على |
|---|---|---|---|
| 1 | Legal Ingestion | تحويل نص قانوني رسمي → Rule-Pack مُصدَّر مُوقَّع | — (مدخلات خارجية) |
| 2 | Rule-Pack Registry | تخزين وإصدار القواعد وخرائط الربط | 1 |
| 3 | Fingerprint | كشف Stack المتجر | — |
| 4 | Scan | إنتاج Findings موحّدة من أي مدخل | 3 |
| 5 | Compliance Eval | حساب Readiness = f(Findings, Profile, Pack) | 2, 4 |
| 6 | AI Fix | شرح + إصلاح مقترح لكل Finding | 5, 7 |
| 7 | Knowledge Graph | تراكم البيانات + تدريب النماذج | 3, 4, 6 |
| 8 | Customer/Dossier | ملف العميل + Timeline مختوم + Dossier | 5, 6 |
| 9 | Billing | الاشتراك والصلاحيات | 8 |
| 10 | Integration | التنبيهات + بوابة Prüfstelle + Changelog | 1, 5, 8 |

## 2.3 نمط النشر (Deployment Pattern)

**Modular Monolith أولاً، لا Microservices.** لماذا: فريق صغير (فرد + شركاء)، والتقسيم المبكر لخدمات يقتل السرعة. لكن **حدود الأنظمة صارمة داخل الـMonolith** (كل نظام Module بواجهة واضحة)، بحيث يمكن استخراج أي نظام كخدمة لاحقاً دون إعادة كتابة. المرشّحون الأوائل للاستخراج عند التوسّع: **النظام 4 (Scan)** و**النظام 1 (Legal Ingestion)** — لأنهما مختلفا ملف الأحمال (Scan = I/O متزامن؛ Ingestion = دفعات مجدولة).

**المهام غير المتزامنة** (فحص، إعادة حساب، Watcher) عبر طابور مهام (Task Queue) منفصل عن دورة الطلب/الاستجابة — إلزامي، لأن الفحص قد يستغرق دقائق.

---

<a name="3"></a>
# 3. نماذج البيانات الأساسية (Core Data Models)

هذه أهم قرارات الوثيقة (P6: Versioned Everything). كل كيان له `id (UUID)`, `created_at`, `updated_at` ما لم يُذكر خلاف ذلك.

## 3.1 خريطة الكيانات (Entity Map)

```
Organization ──< User
     │
     └──< Property ──< StackFingerprint (history)
             │
             ├──< ComplianceProfile (اختيار الولايات)
             │
             └──< Scan ──< Finding ──> Fix
                     │         │
                     │         └──> Rule (المعيار المخالَف)
                     │
                     └──> ReadinessResult (لكل ولاية + موحّد)

RulePack (versioned) ──< Rule ──> RuleMapping (WCAG↔EN↔BFSG↔ADA)
     ▲
     │ يُصدِرها
LegalSource ──< LegalChangeEvent ──> ReviewTask (توقيع خبير)

Property ──< TimelineEvent (append-only, hash-chained) ──> Dossier
Finding ──> KnowledgeEntry (Theme/Component intelligence, anonymized)
Organization ──< Subscription (Stripe)
Scan/Finding ──< ExpertReview (Prüfstelle)
```

## 3.2 كيانات الحساب والملكية

### `Organization`
الحساب الأساسي — تاجر أو وكالة.
- `type: enum(merchant, agency)`
- `name, billing_email, country`
- `plan_id: FK → Subscription`
- `data_sharing_consent: bool` — موافقة تغذية الخندق (P5). افتراضي: false.

### `User`
- `organization_id: FK`
- `email, name, hashed_password`
- `role: enum(owner, member, expert_reviewer, legal_curator, admin)`
- `mfa_enabled: bool`

### `Property`
موقع/متجر خاضع للفحص (وحدة العمل المركزية).
- `organization_id: FK`
- `url: string` — الصفحة الجذر
- `label: string` — اسم ودّي
- `current_fingerprint_id: FK → StackFingerprint` — الأحدث
- `active_profile_id: FK → ComplianceProfile`
- `readiness_current: jsonb` — لقطة سريعة `{ "DE": 82, "US": 74, "combined": 78 }`

## 3.3 كيانات البصمة التقنية

### `StackFingerprint`
لقطة مؤرَّخة لـStack المتجر (P6 — نحفظ التاريخ لكشف Version Drift).
- `property_id: FK`
- `platform: enum(shopware, woocommerce, shopify, magento, wordpress, custom, unknown)`
- `platform_version: string?`
- `theme: {id, name, version?, parent_theme?}` (jsonb)
- `plugins: [{name, version?}]` (jsonb)
- `frontend_framework: enum?(react, vue, angular, none)`
- `component_library: string?`
- `detection_confidence: {platform: float, theme: float, ...}` (jsonb) — درجة الثقة لكل حقل (حاسم للصياغة القانونية الآمنة "الإصدار المحتمل")
- `raw_signals: jsonb` — الأدلة الخام (رؤوس، مسارات أصول) للتدقيق

## 3.4 كيانات القانون والقواعد (القلب — تفصيلها الكامل في القسم 8)

### `LegalSource`
مصدر رسمي مُراقَب.
- `jurisdiction: enum(DE, EU, US)`
- `name, url`
- `source_type: enum(law, regulation, standard, technical_spec, case_law)`
- `extraction_method: enum(html, pdf, api)`
- `check_frequency: enum(daily, weekly, monthly)`
- `last_checked_at, last_content_hash`

### `LegalChangeEvent`
تغيّر مرصود من مصدر.
- `source_id: FK`
- `detected_at`
- `change_type: enum(new_text, version_bump, deadline_change, new_case, editorial_noise)`
- `semantic_diff: jsonb` — الفرق الدلالي (لا البايتات)
- `llm_summary: text` — تلخيص LLM للتغيّر
- `llm_proposed_pack_delta: jsonb` — التحديث المقترح على Rule-Pack
- `status: enum(pending_review, approved, rejected, noise)`
- `review_task_id: FK → ReviewTask`

### `Rule`
معيار وصولية واحد (قابل لإعادة الاستخدام عبر الحزم — P2).
- `code: string` — مثل `wcag-2.2-1.4.3`
- `title, description, wcag_level: enum(A, AA, AAA)?`
- `test_logic: jsonb` — كيف يُكتشف آلياً (أي محرّك/قاعدة) أو `manual_only: true`
- `automatable: bool` — هل يقع ضمن الـ40% الآلية؟
- `source_standard: string` — WCAG/EN 301 549/BITV-extra

### `RulePack`
حزمة قواعد مُصدَّرة لولاية (P2 + P6).
- `jurisdiction: enum(DE, EU, US)`
- `version: string` — مثل `DE-2026.1`
- `effective_from: date` — تاريخ السريان القانوني
- `status: enum(draft, active, superseded)`
- `rule_refs: [{rule_code, weight, mandatory: bool}]` (jsonb) — أي قواعد + ترجيحها القانوني
- `report_template_id: FK`
- `signed_by: FK → User (legal_curator/expert)` — توقيع الاعتماد (P3)
- `signed_at, source_change_events: [FK]` — أثر التدقيق

### `RuleMapping`
الرسم المعرفي القانوني: يربط معياراً عبر الأطر.
- `rule_code: FK`
- `equivalences: jsonb` — `{ "en_301_549": "9.1.4.3", "bfsg": "§...", "ada_508": "..." }`

### `ComplianceProfile`
اختيار العميل للنطاق القانوني (المحور الثاني للـRouter).
- `property_id: FK`
- `selected_jurisdictions: [enum]` — مثل `["DE", "US"]`
- `pack_binding: enum(latest, pinned)` — هل يتبع الأحدث آلياً أم مثبَّت على إصدار؟
- `pinned_versions: jsonb?` — إن pinned
- `combination_mode: enum(union, strictest)` — كيف يُدمج عيب يظهر في ولايتين

## 3.5 كيانات الفحص

### `Scan`
تشغيل فحص واحد.
- `property_id: FK`
- `trigger: enum(manual, scheduled, deploy_webhook, legal_recompute)`
- `input_type: enum(url, theme, plugin, design_system, pdf)`
- `fingerprint_id: FK` — Stack وقت الفحص
- `profile_snapshot: jsonb` — الملف القانوني وإصدارات الحزم وقت الفحص (تجميد — حاسم للتدقيق)
- `status: enum(queued, running, completed, failed)`
- `engine_versions: jsonb` — إصدارات axe/Pa11y/Lighthouse (P6 — إعادة الإنتاجية)

### `Finding`
عيب واحد مُطبَّع (P1 — نفس الشكل من أي مدخل).
- `scan_id: FK`
- `rule_code: FK → Rule`
- `severity: enum(critical, serious, moderate, minor)`
- `location: {selector?, file?, line?, xpath?}` (jsonb) — دقة بمستوى السطر
- `evidence: jsonb` — لقطة/مقتطف DOM/كود
- `source: enum(automated, manual_expert)` — من اكتشفه (للـ40/60)
- `status: enum(open, fixed, wont_fix, false_positive)`
- `knowledge_entry_id: FK?` — إن طُوبق على نمط ثيم معروف

### `Fix`
إصلاح مقترح.
- `finding_id: FK`
- `type: enum(code_patch, config_change, content_change, manual_guidance)`
- `diff: text?` — patch مقترح
- `explanation: text` — شرح Claude بالسياق
- `source: enum(ai_generated, knowledge_graph, expert)` — سُحب من الخندق أم وُلّد؟
- `verified_survived: bool?` — هل صمد بعد إعادة الفحص؟ (تغذية الخندق)

## 3.6 كيانات الخندق المعرفي

### `KnowledgeEntry`
وحدة معرفة متراكمة (Theme/Component Intelligence) — مجهّلة (P5).
- `stack_signature: string` — بصمة الثيم/المكوّن (لا هوية العميل)
- `rule_code: FK`
- `pattern: jsonb` — النمط المتكرر (أين يظهر الخطأ في هذا الثيم)
- `known_fix: jsonb` — الإصلاح المُختبَر
- `occurrence_count: int` — كم متجراً ظهر فيه (بلا هوية)
- `fix_success_rate: float` — نسبة صموده
- `validated_by_expert: bool` — هل أكّده مدقق بشري؟ (حلقة الـ60%)

## 3.7 كيانات الإثبات وإدارة العميل

### `TimelineEvent`
سجل إلحاقي مختوم تسلسلياً (P4 — Notarized Diligence).
- `property_id: FK`
- `sequence_number: int` — تسلسلي لكل property
- `event_type: enum(scan_completed, fix_applied, expert_review_signed, legal_update_applied, statement_generated, readiness_changed)`
- `payload: jsonb` — تفاصيل الحدث
- `content_hash: string` — SHA-256 لمحتوى الحدث
- `prev_hash: string` — hash الحدث السابق (سلسلة)
- `timestamp_token: text?` — RFC 3161 timestamp (ختم زمني موثوق)
- **قاعدة صارمة:** لا UPDATE ولا DELETE على هذا الجدول. Insert فقط.

### `Dossier`
حزمة تدقيق مولّدة (Hero Product).
- `property_id: FK`
- `generated_at`
- `jurisdictions: [enum]` — النطاق المُغطّى
- `pack_versions: jsonb` — أي إصدارات معايير (للختم القانوني)
- `readiness_snapshot: jsonb`
- `timeline_range: {from, to}`
- `pdf_url: string` — الملف المولّد
- `dossier_hash: string` — ختم الحزمة كاملة
- `expert_signature_id: FK?` — إن تضمّن تحققاً بشرياً

### `ExpertReview`
مراجعة Prüfstelle بشرية.
- `scan_id: FK` أو `property_id: FK`
- `reviewer_id: FK → User(expert_reviewer)`
- `manual_findings: [FK → Finding]` — ما اكتشفه يدوياً (الـ60%)
- `signature: jsonb` — التوقيع + المؤهّل + تاريخ
- `insurance_ref: string?` — مرجع تأمينه المهني
- `status: enum(in_progress, signed)`

## 3.8 كيانات الاشتراك

### `Subscription`
- `organization_id: FK`
- `stripe_customer_id, stripe_subscription_id`
- `tier: enum(free_scan, report, monitoring, dev, agency)`
- `seats: int` — للوكالات
- `status: enum(active, past_due, canceled)`

---

<a name="4"></a>
# 4. مواصفة الأنظمة الفرعية العشرة

<a name="sys1"></a>
## النظام 1: Legal Ingestion Engine — محرّك تحديث القوانين

**الأصعب والأكثر أهمية.** يحوّل نصاً قانونياً رسمياً غير مُهيكَل → Rule-Pack مُصدَّر مُوقَّع بشرياً. المشكلة الجوهرية: القوانين تصدر كـPDF وصفحات، لا كـAPI.

### 4.1.1 المكوّنات الداخلية (Pipeline من 4 طبقات)

```
(أ) Source Registry ──▶ (ب) Change Detector ──▶ (ج) LLM Extractor ──▶ (د) Human Review & Publish
   المصادر المُسجّلة      Semantic Diff دوري      يقترح Pack delta      خبير يوقّع → إصدار جديد
```

**(أ) Source Registry** — جدول `LegalSource`. سجل المصادر الرسمية الأولية (~12):

| Jurisdiction | المصادر |
|---|---|
| 🇩🇪 | gesetze-im-internet.de (BFSG/BFSGV) · bundesfachstelle-barrierefreiheit.de · bitvtest.de (Prüfschritte) · bfit-bund.de |
| 🇪🇺 | eur-lex.europa.eu (EAA 2019/882) · etsi.org (EN 301 549) · w3.org (WCAG) |
| 🇺🇸 | ada.gov · federalregister.gov · access-board.gov (508) · w3.org (WCAG) |

**(ب) Change Detector — Semantic Diff (خارج الصندوق):** المشكلة أن Diffing الـHTML الخام يعطي ضجيجاً (تغيّر تنسيق ≠ تغيّر قانون). الحل بثلاث مراحل:
1. **Extract:** استخراج النص القانوني الجوهري فقط (إزالة قوائم التنقّل، الإعلانات، تذييلات) عبر قوالب استخلاص لكل مصدر.
2. **Normalize + Hash:** تطبيع النص (مسافات، ترقيم) → `content_hash`. مقارنة بـ`last_content_hash`.
3. **Semantic classification:** عند اختلاف الـhash، LLM يصنّف: `version_bump` (2.1→2.2) / `deadline_change` / `new_text` / `editorial_noise`. الضجيج التحريري يُهمَل تلقائياً؛ الباقي يمرّ.

**(ج) LLM Extractor:** عند تغيّر جوهري: LLM يقرأ النص + Rule-Pack الحالي → يقترح `llm_proposed_pack_delta` بصيغة مُهيكلة (أي قواعد تُضاف/تُعدَّل/تُلغى، أي مواعيد، أي ترجيح). **لا يُطبَّق** — يُخزَّن كاقتراح.

**(د) Human Review & Publish (P3 — إلزامي قانونياً):** الاقتراح يدخل `ReviewTask` في بوابة الـLegal Curator. الخبير: يوافق/يعدّل/يرفض. عند الموافقة → **Rule-Pack جديد بإصدار جديد** (`DE-2026.2`)، مُوقَّع (`signed_by`)، بأثر تدقيق كامل (`source_change_events`) → يُشغّل النظام 10 (Changelog + إعادة الحساب).

### 4.1.2 قرار الأتمتة (مُتفَّق عليه)
نصف-آلي أول سنة: ~12 مصدراً، تغيّرات نادرة (مرات/سنة). الخبير يراجع تنبيهات أسبوعية. النظام يتعلّم من قراراته (أي تصنيفات كانت ضجيجاً) لأتمتة تدريجية. **الأتمتة الكاملة من اليوم الأول فخّ** — وتخالف P3.

### 4.1.3 مخرجات
`RulePack` جديد (active) + `LegalChangeEvent` مُصدَّق + تشغيل إعادة حساب Readiness لكل property متأثّر.

---

<a name="sys2"></a>
## النظام 2: Rule-Pack Registry — سجل حزم القواعد

**بنية البيانات المحورية (P2).** يخزّن ويُصدِر القواعد وخرائط الربط. تفصيله الكامل في القسم 8.

### 4.2.1 المسؤوليات
- تخزين `Rule` (قابل لإعادة الاستخدام) و`RulePack` (versioned, jurisdiction-scoped) و`RuleMapping` (الرسم المعرفي).
- **Resolution API داخلي:** `resolve(profile, date) → active RuleSet` — يحسم أي قواعد تنطبق لملف قانوني معيّن في تاريخ معيّن.
- **إصدار WCAG 2.1→2.2 عملياً:** Pack جديد `EU-2026.2` يشير لنفس الـRules السابقة + 9 جديدة، `effective_from` = تاريخ نشر EN 301 549 المحدّث. القديم يصبح `superseded` لا يُحذف. صفر Deploy.

### 4.2.2 قاعدة الحسم (Resolution)
```
دخل: ComplianceProfile { jurisdictions: [DE, US], mode: strictest }
1. لكل ولاية: اجلب RulePack النشط (أو المثبَّت إن pinned) في التاريخ المطلوب.
2. وحّد القواعد عبر RuleMapping (نفس المعيار في ولايتين = عقدة واحدة، ترجيحان).
3. طبّق combination_mode: strictest = خذ أعلى ترجيح؛ union = اجمع الكل.
4. أخرج RuleSet موحّد + مصفوفة "أي قاعدة لأي ولاية".
```

---

<a name="sys3"></a>
## النظام 3: Fingerprint Engine — محرّك البصمة (المُوجِّه)

يكشف Stack المتجر في ثانيتين. **مُوجِّه الـRouter التقني.**

### 4.3.1 مصادر الكشف (تُدمج بثقة مرجّحة)
| الإشارة | ماذا تكشف |
|---|---|
| HTTP headers (`X-Powered-By`, `Server`, cookies) | المنصة أحياناً |
| Asset paths (`/wp-content/`, `/media/theme/`, `/apps/`) | المنصة + الثيم |
| DOM markers (meta generator, class prefixes) | المنصة + الثيم + الإصدار |
| JS/CSS fingerprints (hashes معروفة، أسماء bundles) | الإطار + المكتبة + الإضافات |
| Known-signature DB | مطابقة توقيعات ثيمات/إضافات معروفة |

### 4.3.2 مخرج حاسم: درجة الثقة
كل حقل يُرفَق بـ`detection_confidence`. **هذا يخدم الصياغة القانونية الآمنة مباشرة:** "الإصدار المحتمل Y" (لا "الإصدار Y" قاطعاً) — يمنع فقدان المصداقية من أول رسالة. الثيم غير المعروف = `unknown` بثقة منخفضة، لا تخمين.

### 4.3.3 حلقة التعلّم
كل fingerprint مؤكَّد (بمطابقة لاحقة أو تأكيد بشري) يُثري Known-signature DB → دقة متزايدة (P7).

---

<a name="sys4"></a>
## النظام 4: Multi-Input Scan Engine — محرّك الفحص متعدد المدخلات

**تجسيد P1 (Normalize-then-Process).** كل مدخلاتك في نظام واحد عبر Adapters، تُنتج جميعها `Finding` موحّداً.

### 4.4.1 المُحوِّلات (Adapters)
| Adapter | التقنية | ملاحظة |
|---|---|---|
| **URL Adapter** | Crawler (Playwright) + axe-core + Pa11y + Lighthouse | فحص حيّ؛ يستدعي Fingerprint |
| **Theme Adapter** | Static Analysis على الكود المصدري | أدق من الحيّ — يرى ما لا يُعرَض |
| **Plugin Adapter** | Static Analysis | نفس المبدأ |
| **Design System Adapter** | فحص المكوّن معزولاً (Storybook-style render) | يصلح المصدر = يصلح كل النسخ |
| **PDF Adapter** | فحص PDF/UA | مستندات |

### 4.4.2 التدفّق الموحّد
```
مدخل → Adapter مناسب → استخراج مشاكل خام (بلغة الأداة)
     → Normalizer: تحويل كل مشكلة إلى Finding { rule_code, severity, location, evidence }
     → ربط بـRule عبر جدول المطابقة (axe-rule → wcag-code)
     → [إثراء] مطابقة على KnowledgeEntry إن كان الثيم معروفاً
     → تخزين Findings مربوطة بالـScan
```

### 4.4.3 قرار معماري
**الـNormalizer هو القلب.** جدول مطابقة `engine_issue_id → rule_code` يجعل إضافة محرّك جديد (أو مدخل جديد) مجرد توسيع للمطابقة، لا تغيير للمحرّكات التالية. المحرّك 5 لا يعرف مصدر الـFinding إطلاقاً.

---

<a name="sys5"></a>
## النظام 5: Compliance Evaluation Engine — محرّك تقييم الامتثال

القلب الحسابي. `Readiness = f(Findings, ComplianceProfile, RuleSet)`.

### 4.5.1 التدفّق
```
1. اجلب Findings الخاصة بالـScan.
2. اجلب RuleSet المحسوم من النظام 2 (حسب Profile + التاريخ).
3. لكل ولاية مختارة: احسب Readiness = دالة تجميع (Findings المخالِفة × ترجيحها × شدّتها) مقابل RuleSet.
4. أخرج: { "DE": 82, "US": 74, "combined": 78 } + قائمة الفجوات مرتّبة بالأولوية القانونية.
```

### 4.5.2 نموذج النقاط (Readiness Score)
- ليس "عدد الأخطاء" بل درجة تُدار كالدَّين التقني: 0-100.
- **الترجيح القانوني:** خطأ حرج في DE قد يوزن أثقل منه في US (من `rule_refs.weight` في الحزمة). العيب نفسه، وزنان.
- **الدمج (combination_mode):** `strictest` = العيب يُحسب بأعلى ترجيح بين الولايتين؛ `union` = يُحسب لكليهما.
- **الشفافية:** كل نقطة مفقودة تُرجَع لقاعدة مُسمّاة بإصدارها ("−4 بسبب wcag-2.2-1.4.3 [DE-2026.2]") — أساس الـDossier القانوني.

### 4.5.3 قاعدة صارمة
Readiness دائماً **مقابل إصدار حزمة مُسمّى وتاريخ** (`profile_snapshot` في الـScan). لا رقم مطلق عائم — لأن القانون يتغيّر، والرقم بلا معيار وإصدار بلا قيمة قانونية.

---

<a name="sys6"></a>
## النظام 6: AI Fix & Explanation Engine

لكل Finding: شرح بالسياق + إصلاح مقترح.

### 4.6.1 التدفّق (يستفيد من الخندق أولاً)
```
لكل Finding:
1. هل يوجد KnowledgeEntry مطابق (ثيم معروف + نفس القاعدة)؟
   └─ نعم → اسحب known_fix المُختبَر (source=knowledge_graph). أرخص وأدق. [P7]
   └─ لا  → ولّد Fix عبر Claude (source=ai_generated) مع سياق الكود.
2. ولّد شرحاً بالسياق (لماذا هذا خطأ، لمن يضر).
3. أخرج Fix { type, diff?, explanation }.
```

### 4.6.2 قرار المسؤولية
Fix دائماً **نص/patch مقترح، لا Auto-PR** (تخفيف مخاطر المسؤولية). التطبيق قرار العميل + تحقق بشري قبل الدمج.

### 4.6.3 حلقة التغذية
عند إعادة فحص property بعد تطبيق Fix: إن اختفى الـFinding → `verified_survived=true` → يُرفع `fix_success_rate` في KnowledgeEntry. **هكذا يتعلّم الخندق أي إصلاحات تصمد فعلاً.**

---

<a name="sys7"></a>
## النظام 7: Knowledge Graph & Data Moat — الخندق المعرفي

**صانع القيمة طويلة الأمد.** يراكم البيانات ويدرّب النماذج.

### 4.7.1 خطوط البيانات الثلاثة (تتقاطع)
| المصدر | العمق | الآلية |
|---|---|---|
| **Inference** (كل فحص) | واسع سطحي | fingerprint + أنماط أخطاء + هل صمد الإصلاح |
| **Ground Truth** (شراكات) | عميق صحيح | مصدر ثيمات من مطوّريها + وكالات (مجهّل) |
| **Expert Loop** (Prüfstelle) | الأثمن | الـ60% اليدوية تُغذّى كـLabels لتدريب الكشف الآلي |

### 4.7.2 البنية
- **تخزين:** رسم `KnowledgeEntry` يربط `stack_signature ↔ rule ↔ pattern ↔ fix ↔ ترجيح`.
- **تجهيل إلزامي (P5):** `stack_signature` بصمة تقنية لا هوية عميل. لا URL، لا اسم منظمة في الخندق. الربط بالعميل يبقى في النظام 8 معزولاً.
- **الموافقة:** فقط منظمات بـ`data_sharing_consent=true` تغذّي الخندق.

### 4.7.3 تدريب النماذج (تدريجي)
مع نضج البيانات: نماذج لـ(1) كشف الثيم من إشارات جزئية، (2) توقّع أخطاء ثيم قبل فحصه، (3) ترتيب الإصلاحات بنجاحها. **حلقة الخبير هي الميزة المركّبة:** منافس آلي بالكامل سطحي، وبشري بالكامل لا يتوسّع؛ أنت تجمع.

### 4.7.4 قيمة تجارية جانبية
`stack_signature` عبر آلاف المتاجر = **إحصاء الطبقة التقنية للتجارة** (Census) — أصل بيانات يتجاوز الوصولية (مسار BuiltWith/Wappalyzer). مؤجّل كمنتج، لكن البنية تجمعه من اليوم الأول.

---

<a name="sys8"></a>
## النظام 8: Customer & Dossier Management

إدارة العميل + سجل الإثبات (Hero Product).

### 4.8.1 الـTimeline المختوم (P4)
كل حدث ذي دلالة قانونية → `TimelineEvent` إلحاقي:
```
event → احسب content_hash (SHA-256)
      → prev_hash = hash الحدث السابق لنفس الـproperty (سلسلة)
      → [اختياري] اطلب RFC 3161 timestamp token من TSA موثوقة
      → INSERT فقط (لا UPDATE/DELETE أبداً)
```
النتيجة: سلسلة لا يمكن العبث بها بأثر رجعي → تثبت أن الاجتهاد لم يُلفَّق ليلة الاستفسار (Notarized Diligence). التحقق: أعد حساب السلسلة، أي كسر يُكشف.

### 4.8.2 Audit-Ready Dossier (زر واحد)
```
Generate Audit Package →
  اجمع: كل Scans + Findings + Fixes بتواريخها
      + Statement (§ البيان)
      + Readiness عبر الزمن (Timeline)
      + الفجوات المتبقية + خطة معالجتها
      + إصدارات الحزم المستخدمة (الختم القانوني: "مقابل BFSG/EN 301 549 V3.2.1")
      + [إن وُجد] توقيع Prüfstelle
  → ولّد PDF → اختم dossier_hash → خزّن Dossier
```
**هذا ما يُدفَع مقابله:** الجاهزية في 60 ثانية يوم يصل الخطاب الرقابي.

### 4.8.3 معالجة الوكالات
Agency ترى كل properties عملائها في لوحة واحدة، تولّد Dossier لكل منها، تدير مقاعد. (White-Label الكامل مؤجّل.)

---

<a name="sys9"></a>
## النظام 9: Billing & Access

Stripe + المستويات + الصلاحيات.

### 4.9.1 المستويات
| Tier | يفتح |
|---|---|
| free_scan | فحص واحد + Readiness (بلا Dossier كامل) — الاكتساب |
| report | Dossier لمرة واحدة |
| monitoring | فحص مستمر + Changelog + Timeline حيّ |
| dev | + مدخلات Theme/Plugin/Design System |
| agency | مقاعد متعددة + إدارة عملاء |

### 4.9.2 نموذج الصلاحيات (RBAC)
Middleware يتحقق: (الدور × المستوى) → السماح/المنع. الوكالة تدير أدواراً فرعية لمقاعدها.

---

<a name="sys10"></a>
## النظام 10: Integration & Notification

التنبيهات + بوابة Prüfstelle + Changelog.

### 4.10.1 المكوّنات
- **Regulatory Changelog:** عند Rule-Pack جديد → تنبيه العملاء المتأثّرين + إعادة حساب Readiness + إدخال Timeline (`legal_update_applied`). "المعيار تحدّث → Readiness من 88 إلى 79 → هذه 9 فجوات جديدة."
- **Deploy/Drift Alerts:** هبوط Readiness بعد Deploy (webhook اختياري) أو تحديث ثيم.
- **Prüfstelle Portal:** واجهة الخبير — طابور Findings للمراجعة اليدوية + توقيع + مراجعة تغييرات القانون (النظام 1د).
- **GitHub Action (مؤجّل):** تعليق على الـPR + إصلاح مقترح.

---

<a name="5"></a>
# 5. تصميم الـAPI الخارجي (REST)

مبادئ: REST مورد-محور · JSON · مصادقة `Bearer JWT` · إصدار عبر `/v1/` · OpenAPI مُولَّد تلقائياً من FastAPI/Pydantic. الفحص وإعادة الحساب **غير متزامنة** (تُرجع `202 + task_id`، النتيجة عبر polling أو webhook).

## 5.1 المصادقة والحساب
| Method | Endpoint | الوصف |
|---|---|---|
| POST | `/v1/auth/register` | إنشاء منظمة + مالك |
| POST | `/v1/auth/login` | JWT |
| GET | `/v1/orgs/me` | المنظمة الحالية + الاشتراك |
| PATCH | `/v1/orgs/me` | تعديل (يشمل `data_sharing_consent`) |
| GET/POST | `/v1/users` | إدارة المستخدمين (RBAC) |

## 5.2 الـProperties والملف القانوني
| Method | Endpoint | الوصف |
|---|---|---|
| GET/POST | `/v1/properties` | قائمة/إنشاء متجر |
| GET | `/v1/properties/{id}` | تفاصيل + Readiness حالي |
| POST | `/v1/properties/{id}/fingerprint` | كشف Stack (202) |
| GET | `/v1/properties/{id}/fingerprints` | تاريخ البصمات (Drift) |
| PUT | `/v1/properties/{id}/compliance-profile` | اختيار الولايات + mode (المحور الثاني) |

## 5.3 الفحص والنتائج
| Method | Endpoint | الوصف |
|---|---|---|
| POST | `/v1/properties/{id}/scans` | بدء فحص — body: `{input_type, input_ref}` (202 + task_id) |
| GET | `/v1/scans/{id}` | حالة + Readiness (عند الاكتمال) |
| GET | `/v1/scans/{id}/findings` | الفجوات (فلترة بالولاية/الشدة) |
| GET | `/v1/findings/{id}/fix` | الإصلاح المقترح + الشرح |
| PATCH | `/v1/findings/{id}` | تحديث الحالة (fixed/wont_fix/false_positive) |

## 5.4 الإثبات والـDossier
| Method | Endpoint | الوصف |
|---|---|---|
| GET | `/v1/properties/{id}/timeline` | السجل المختوم |
| POST | `/v1/properties/{id}/dossier` | توليد حزمة تدقيق (Generate Audit Package) |
| GET | `/v1/dossiers/{id}` | تحميل PDF + التحقق من الختم |
| POST | `/v1/properties/{id}/statement` | مولّد بيان الوصولية (§) |

## 5.5 بوابة Prüfstelle (أدوار الخبير)
| Method | Endpoint | الوصف |
|---|---|---|
| GET | `/v1/expert/review-queue` | Findings/scans بانتظار مراجعة بشرية |
| POST | `/v1/expert/scans/{id}/manual-findings` | إضافة اكتشافات يدوية (الـ60%) |
| POST | `/v1/expert/scans/{id}/sign` | توقيع التحقق (+ insurance_ref) |

## 5.6 بوابة القانون (Legal Curator)
| Method | Endpoint | الوصف |
|---|---|---|
| GET | `/v1/legal/change-events?status=pending_review` | تغييرات مرصودة بانتظار التصديق |
| POST | `/v1/legal/change-events/{id}/approve` | اعتماد → إصدار Rule-Pack جديد |
| POST | `/v1/legal/change-events/{id}/reject` | رفض/ضجيج |
| GET | `/v1/legal/rule-packs?jurisdiction=DE` | إصدارات الحزم |

## 5.7 Webhooks (خارجة)
- `scan.completed` · `readiness.changed` · `legal.pack_published` · `dossier.ready`
- Stripe webhooks داخلة على `/v1/billing/webhook`.

---

<a name="6"></a>
# 6. مخطط قاعدة البيانات (PostgreSQL)

نمط: علاقات صارمة للكيانات المستقرة (عملاء، فواتير، Timeline) + **JSONB للبيانات شبه-المرنة** (Rule-Packs، Fingerprints، Findings). فهارس على المفاتيح الأجنبية و`jsonb_path_ops` حيث يُستعلَم عن JSONB.

## 6.1 جداول الحساب
```sql
organizations (
  id UUID PK, type TEXT, name TEXT, billing_email TEXT,
  country TEXT, data_sharing_consent BOOL DEFAULT false,
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
)
users (
  id UUID PK, organization_id UUID FK, email TEXT UNIQUE,
  name TEXT, hashed_password TEXT, role TEXT, mfa_enabled BOOL
)
subscriptions (
  id UUID PK, organization_id UUID FK, stripe_customer_id TEXT,
  stripe_subscription_id TEXT, tier TEXT, seats INT DEFAULT 1, status TEXT
)
```

## 6.2 جداول الملكية والبصمة
```sql
properties (
  id UUID PK, organization_id UUID FK, url TEXT, label TEXT,
  current_fingerprint_id UUID FK, active_profile_id UUID FK,
  readiness_current JSONB   -- {"DE":82,"US":74,"combined":78}
)
stack_fingerprints (
  id UUID PK, property_id UUID FK, platform TEXT, platform_version TEXT,
  theme JSONB, plugins JSONB, frontend_framework TEXT,
  component_library TEXT, detection_confidence JSONB, raw_signals JSONB,
  created_at TIMESTAMPTZ
)
compliance_profiles (
  id UUID PK, property_id UUID FK,
  selected_jurisdictions TEXT[],       -- {DE,US}
  pack_binding TEXT DEFAULT 'latest',  -- latest | pinned
  pinned_versions JSONB, combination_mode TEXT DEFAULT 'strictest'
)
```

## 6.3 جداول القانون والقواعد (القلب)
```sql
legal_sources (
  id UUID PK, jurisdiction TEXT, name TEXT, url TEXT, source_type TEXT,
  extraction_method TEXT, check_frequency TEXT,
  last_checked_at TIMESTAMPTZ, last_content_hash TEXT
)
legal_change_events (
  id UUID PK, source_id UUID FK, detected_at TIMESTAMPTZ, change_type TEXT,
  semantic_diff JSONB, llm_summary TEXT, llm_proposed_pack_delta JSONB,
  status TEXT DEFAULT 'pending_review', review_task_id UUID
)
rules (
  id UUID PK, code TEXT UNIQUE, title TEXT, description TEXT,
  wcag_level TEXT, test_logic JSONB, automatable BOOL, source_standard TEXT
)
rule_packs (
  id UUID PK, jurisdiction TEXT, version TEXT, effective_from DATE,
  status TEXT,                 -- draft | active | superseded
  rule_refs JSONB,             -- [{rule_code, weight, mandatory}]
  report_template_id UUID, signed_by UUID FK, signed_at TIMESTAMPTZ,
  source_change_events UUID[]  -- أثر التدقيق
)
rule_mappings (
  id UUID PK, rule_code TEXT FK, equivalences JSONB
  -- {"en_301_549":"9.1.4.3","bfsg":"§...","ada_508":"..."}
)
```

## 6.4 جداول الفحص
```sql
scans (
  id UUID PK, property_id UUID FK, trigger TEXT, input_type TEXT,
  fingerprint_id UUID FK,
  profile_snapshot JSONB,   -- تجميد الملف + إصدارات الحزم وقت الفحص
  status TEXT, engine_versions JSONB, created_at TIMESTAMPTZ
)
findings (
  id UUID PK, scan_id UUID FK, rule_code TEXT FK, severity TEXT,
  location JSONB, evidence JSONB, source TEXT,   -- automated|manual_expert
  status TEXT DEFAULT 'open', knowledge_entry_id UUID
)
fixes (
  id UUID PK, finding_id UUID FK, type TEXT, diff TEXT, explanation TEXT,
  source TEXT,                 -- ai_generated|knowledge_graph|expert
  verified_survived BOOL
)
readiness_results (
  id UUID PK, scan_id UUID FK, jurisdiction TEXT, score INT,
  gaps JSONB, computed_against_pack TEXT   -- الإصدار المُسمّى
)
```

## 6.5 جداول الخندق
```sql
knowledge_entries (
  id UUID PK, stack_signature TEXT, rule_code TEXT FK, pattern JSONB,
  known_fix JSONB, occurrence_count INT DEFAULT 1, fix_success_rate FLOAT,
  validated_by_expert BOOL DEFAULT false
  -- ملاحظة: لا FK لأي property/organization (تجهيل P5)
)
```

## 6.6 جداول الإثبات (Append-Only)
```sql
timeline_events (
  id UUID PK, property_id UUID FK, sequence_number INT,
  event_type TEXT, payload JSONB,
  content_hash TEXT, prev_hash TEXT, timestamp_token TEXT,
  created_at TIMESTAMPTZ,
  UNIQUE(property_id, sequence_number)
)
-- قيد على مستوى التطبيق + trigger DB يمنع UPDATE/DELETE

dossiers (
  id UUID PK, property_id UUID FK, generated_at TIMESTAMPTZ,
  jurisdictions TEXT[], pack_versions JSONB, readiness_snapshot JSONB,
  timeline_range JSONB, pdf_url TEXT, dossier_hash TEXT, expert_signature_id UUID
)
expert_reviews (
  id UUID PK, scan_id UUID FK, property_id UUID FK, reviewer_id UUID FK,
  manual_findings UUID[], signature JSONB, insurance_ref TEXT, status TEXT
)
```

---

<a name="7"></a>
# 7. الأمن والخصوصية (DSGVO / Privacy by Design)

**حاسم لأنك تجمع بيانات مواقع عملاء تحت DSGVO.** (P5 — لا يمكن إضافة هذا لاحقاً.)

## 7.1 فصل البيانات (Data Separation)
| النطاق | يحوي | الوصول |
|---|---|---|
| **Identified** (النظام 8) | العميل، URL، Findings مربوطة بالهوية | العميل + Admin فقط |
| **Anonymized** (النظام 7) | `stack_signature`، أنماط، إصلاحات — **بلا هوية** | يغذّي الخندق والتدريب |

**قاعدة صارمة:** لا FK من `knowledge_entries` إلى أي `property/organization`. الجسر الوحيد `stack_signature` (بصمة تقنية، لا هوية). التجهيل يحدث **قبل** دخول الخندق، لا بعده.

## 7.2 الموافقة (Consent)
- الخندق يتغذّى فقط من منظمات `data_sharing_consent=true`.
- الموافقة صريحة، قابلة للسحب. عند السحب: يُوقَف تدفّق المنظمة (البيانات المجهّلة السابقة غير قابلة للربط بها أصلاً).

## 7.3 الأمن التقني
- كلمات المرور: Argon2. المصادقة: JWT قصير العمر + refresh. MFA للأدوار الحسّاسة (expert, curator, admin).
- التشفير: TLS أثناء النقل؛ تشفير عند الراحة للحقول الحسّاسة.
- RBAC على كل endpoint. عزل بيانات المنظمات (Row-Level Security على `organization_id`).
- أسرار عبر Secrets Manager، لا في الكود.

## 7.4 سلامة الإثبات (Evidence Integrity)
- `timeline_events`: Insert فقط (trigger DB يمنع UPDATE/DELETE). سلسلة hash + RFC 3161 timestamp من TSA موثوقة.
- الـDossier مختوم؛ أي تعديل يُكشف بإعادة حساب الـhash.

## 7.5 حدود المسؤولية في التصميم
- الطبقة الآلية = أداة (مسؤولية Software قياسية).
- التوقيع البشري على الـPrüfstelle بتأمينه المهني (`insurance_ref`).
- لا ادعاء "Certification/Guaranteed" في أي مخرَج — فقط Assessment/Conformance Report/Documentation.

---

<a name="8"></a>
# 8. الطبقة القانونية — Compliance Profile Schema (القلب)

**هذا القسم هو أهم ما في الوثيقة.** يحسم كيف تُخزَّن المعايير كبيانات مُصدَّرة، وكيف يعمل تحديث WCAG 2.1→2.2 كتغيير نسخة لا إعادة بناء.

## 8.1 المبدأ: طبقتان (Rules-as-Data + Schema-as-Code)
- **المحتوى (البيانات):** كل Rule/RulePack مستند JSONB في DB. تحديث = صف جديد. لا Deploy.
- **البنية (الكود):** كل مستند محكوم بـ**JSON Schema / Pydantic Model** صارم مُراجَع في الكود. خبير غير تقني لا يستطيع إدخال بيانات مشوَّهة تكسر النظام.

هذا يفصل منطق الأعمال (يتغيّر أسبوعياً بالبيانات) عن كود التطبيق (يتغيّر ببطء) — نمط Rule Engines الحديث.

## 8.2 كائن `Rule` (المعيار الذرّي)
قابل لإعادة الاستخدام عبر كل الحزم. يُعرَّف مرة، يُشار إليه من ولايات متعددة.
```json
{
  "code": "wcag-2.2-1.4.3",
  "title": "Contrast (Minimum)",
  "source_standard": "WCAG 2.2",
  "wcag_level": "AA",
  "automatable": true,
  "test_logic": {
    "engine": "axe-core",
    "rule_id": "color-contrast",
    "manual_fallback": false
  },
  "description": "نص وصورة نص لهما نسبة تباين 4.5:1 على الأقل..."
}
```
القاعدة اليدوية البحتة (الـ60%): `"automatable": false, "test_logic": {"manual_only": true, "expert_guidance": "..."}`.

## 8.3 كائن `RulePack` (الحزمة المُصدَّرة)
جوهر النظام. حزمة قواعد لولاية، بإصدار وتاريخ سريان.
```json
{
  "jurisdiction": "DE",
  "version": "DE-2026.2",
  "effective_from": "2026-06-28",
  "status": "active",
  "legal_basis": "BFSG + BFSGV + BITV 2.0 → EN 301 549 V3.2.1",
  "rule_refs": [
    { "rule_code": "wcag-2.2-1.4.3", "weight": 9, "mandatory": true },
    { "rule_code": "wcag-2.2-2.1.1", "weight": 10, "mandatory": true },
    { "rule_code": "wcag-2.2-2.4.11", "weight": 6, "mandatory": true }
  ],
  "report_template_id": "tmpl-de-conformance",
  "signed_by": "curator-uuid",
  "signed_at": "2026-06-01T...",
  "source_change_events": ["evt-uuid-1"]
}
```
- `weight`: الترجيح القانوني (0-10) — **يختلف بين الولايات لنفس القاعدة**.
- `mandatory`: هل إلزامية في هذه الولاية؟ (بعض معايير AAA اختيارية).
- `signed_by/source_change_events`: أثر التدقيق الكامل (P3) — من اعتمد، وبناءً على أي تغيّر قانوني.

## 8.4 كائن `ComplianceProfile` (اختيار العميل — المحور الثاني للـRouter)
```json
{
  "property_id": "prop-uuid",
  "selected_jurisdictions": ["DE", "US"],
  "pack_binding": "latest",
  "combination_mode": "strictest"
}
```
- `selected_jurisdictions`: ولاية واحدة أو دمج. هذا الحقل وحده يفعّل "ألماني / أوروبي / أمريكي / دمج".
- `pack_binding: latest` = يتبع أحدث حزمة نشطة آلياً (Readiness تتحدّث مع القانون). `pinned` = مثبَّت على إصدار (لتجميد تقرير لحظة معيّنة).
- `combination_mode`: `strictest` (أعلى ترجيح) أو `union` (اجمع الكل).

## 8.5 كائن `RuleMapping` (الرسم المعرفي القانوني)
يربط معياراً واحداً عبر الأطر — يمنع ازدواج الحساب عند الدمج.
```json
{
  "rule_code": "wcag-2.2-1.4.3",
  "equivalences": {
    "en_301_549": "9.1.4.3",
    "bfsg": "via BITV 2.0 → EN 301 549 §9",
    "ada_title_ii": "WCAG 2.1 AA §1.4.3",
    "section_508": "501 (Web) → WCAG 2.0 AA §1.4.3"
  }
}
```
عند دمج DE+US: `wcag-2.2-1.4.3` عقدة واحدة، تُحسب بترجيح DE (9) أو US (حسب mode)، لا مرتين.

## 8.6 آلية تحديث WCAG 2.1 → 2.2 (الاختبار الحاسم)
السيناريو الفعلي (جارٍ الآن في EN 301 549):
```
1. Legal Watcher يرصد نشر EN 301 549 المحدّث (version_bump).
2. LLM يقترح delta: "أضف 9 قواعد جديدة (2.4.11, 2.4.12, 2.4.13, 2.5.7, 2.5.8, 3.2.6, 3.3.7, 3.3.8, ...)."
3. Legal Curator يراجع ويصادق.
4. النظام يُنشئ RulePack جديد:
   - EU-2026.1 (قديم): status → superseded (لا يُحذف)
   - EU-2026.2 (جديد): يشير لنفس قواعد 2.1 + 9 قواعد 2.2 الجديدة
     effective_from = تاريخ النشر الرسمي
5. كل property بـpack_binding=latest → إعادة حساب Readiness آلياً.
6. Changelog: "المعيار تحدّث إلى WCAG 2.2 → Readiness من 88 إلى 79 → 9 فجوات جديدة → هذه الإصلاحات."
```
**صفر Deploy. صفر تغيير كود.** فقط بيانات جديدة + توقيع. هذا هو المكسب الكامل لقرار Rules-as-Data.

## 8.7 خوارزمية الحسم (Resolution) — كيف يستخدم المحرّك 5 كل هذا
```
resolve(profile, date):
  packs = []
  for j in profile.selected_jurisdictions:
     if profile.pack_binding == 'pinned':
        pack = get_pack(j, profile.pinned_versions[j])
     else:
        pack = get_active_pack(j, on_date=date)   # الأحدث الساري في التاريخ
     packs.append(pack)

  ruleset = {}
  for pack in packs:
     for ref in pack.rule_refs:
        node = canonical_rule(ref.rule_code)      # عبر RuleMapping
        if node in ruleset:                        # ظهر في ولاية أخرى
           merge_weight(ruleset[node], ref.weight, profile.combination_mode)
        else:
           ruleset[node] = { rule: node, weights: {pack.jurisdiction: ref.weight} }

  return ruleset   # + مصفوفة "أي قاعدة لأي ولاية" للتقرير
```

## 8.8 قوالب التقارير (Report Templates)
كل ولاية لها `report_template` (VPAT-Stil للأمريكي، Conformance Report للألماني/الأوروبي). القالب بيانات أيضاً (لا كود)، يربط الـReadiness + الفجوات + إصدار الحزمة بصيغة الولاية القانونية. الدمج يُنتج تقريراً متعدد الأقسام (قسم لكل ولاية + ملخّص موحّد).

---

<a name="9"></a>
# 9. تدفّقات المستخدم الرئيسية (User Flows)

## 9.1 Flow A — تاجر جديد: من URL إلى Dossier
```
1. تسجيل → إنشاء Property (URL)
2. POST fingerprint → كشف Stack (ثانيتان) → عرض "متجركم على Shopware + Theme X (محتمل v3)"
3. اختيار Compliance Profile: 🇩🇪 (افتراضي حسب موقع العميل) — أو دمج
4. POST scan (input=url) → [async] Crawl + محرّكات + Normalize → Findings
5. Compliance Eval → Readiness "DE: 61/100" + فجوات مرتّبة بالأولوية القانونية
6. لكل فجوة: شرح + Fix مقترح (سُحب من الخندق إن الثيم معروف)
7. Timeline يسجّل scan_completed (مختوم)
8. ترقية للدفع → POST dossier → Audit Package PDF مختوم
```

## 9.2 Flow B — انتشار تغيّر قانوني (الخندق الجديد)
```
1. [مجدول] Watcher يفحص EN 301 549 → Semantic Diff يرصد version_bump
2. LLM يقترح pack_delta (9 قواعد 2.2)
3. Legal Curator يراجع في البوابة → يصادق
4. RulePack EU-2026.2 يُنشأ (القديم superseded)
5. [async] إعادة حساب Readiness لكل property بـbinding=latest متأثّر
6. Changelog notification: "المعيار تحدّث → Readiness ↓ → 9 فجوات جديدة"
7. Timeline يسجّل legal_update_applied (مختوم) — إثبات أنك واكبت القانون
```

## 9.3 Flow C — مراقبة مستمرة + كشف Drift
```
1. [مجدول أو deploy webhook] إعادة فحص Property
2. مقارنة Fingerprint الجديد بالسابق → كشف تحديث ثيم/إصدار (Drift)
3. Readiness جديد → إن هبط: تنبيه "ظهرت فجوات بعد Deploy الأمس"
4. Timeline يسجّل التغيّر — يبرّر الاشتراك الشهري (الملف يجب أن يبقى حياً)
```

## 9.4 Flow D — مراجعة الخبير (Prüfstelle، الـ60%)
```
1. عميل على مستوى monitoring+ يطلب تحققاً بشرياً سنوياً
2. الخبير يفتح review-queue → يفحص يدوياً ما لا يكتشفه الآلي
3. POST manual-findings → تُضاف Findings (source=manual_expert)
4. POST sign → توقيع + insurance_ref → Timeline: expert_review_signed
5. الاكتشافات اليدوية (مجهّلة) تُغذّي الخندق كـLabels لتحسين الكشف الآلي
6. Dossier التالي يتضمّن التوقيع البشري المؤمَّن
```

## 9.5 Flow E — وكالة (متعدد المتاجر)
```
1. Agency org → إضافة properties عملائها (مقاعد)
2. لوحة موحّدة: Readiness كل المتاجر
3. توليد Dossier لكل عميل بضغطة
4. اكتشافات المتاجر (مجهّلة) تُثري الخندق → إصلاحات أدق للجميع (Data Co-op)
```

---

<a name="10"></a>
# 10. المكدّس التقني والبنية التحتية

## 10.1 المكدّس (مع التبرير)
| الطبقة | التقنية | التبرير |
|---|---|---|
| **Backend API** | Python + FastAPI | يطابق خبرتك؛ OpenAPI تلقائي؛ async يقارب أداء Node في I/O |
| **NLP/LLM/ML** (النظام 1، 7) | Python (نفس البيئة) | الأقوى لأحمال الاستخلاص والتدريب — لا جسر لغوي |
| **قاعدة البيانات** | PostgreSQL | JSONB (Rule-Packs) + علاقات صارمة (عملاء/Timeline) في محرّك واحد |
| **الواجهة** | Next.js + TypeScript | SSR، تجربة حديثة، تكامل جيد مع REST/OpenAPI |
| **مهام حيّة متزامنة** | Node.js (اختياري) | Crawling/Fingerprint المتزامن عالي الـI/O إن لزم |
| **Task Queue** | Celery + Redis (أو RQ) | الفحص/إعادة الحساب/Watcher غير متزامنة — إلزامي |
| **LLM** | Claude API | الشرح، اقتراح pack_delta، توليد Fix |
| **محرّكات الفحص** | axe-core, Pa11y, Lighthouse, Playwright | مفتوحة — تُبتلع كمدخلات في الـNormalizer |
| **التخزين** | Object storage (PDF/Dossiers) | الملفات المولّدة |
| **الختم الزمني** | RFC 3161 TSA | سلامة Timeline |

## 10.2 قرارات بنيوية
- **Modular Monolith** (لا Microservices) — راجع 2.3. الحدود صارمة، الاستخراج لاحق.
- **Task Queue منفصل** عن دورة الطلب — الفحص دقائق لا ثوانٍ.
- **Row-Level Security** على `organization_id` — عزل بيانات العملاء.
- **Migrations مُدارة** (Alembic) — لكن تحديث القواعد **ليس** migration (بيانات لا Schema) — هذا جوهر Rules-as-Data.

## 10.3 المراقبة والتشغيل
- Logging مُهيكَل + tracing على المهام غير المتزامنة.
- مراقبة صحة الـWatcher (تنبيه إن فشل فحص مصدر).
- Rate limiting على الفحص (منع إساءة الاستخدام).

---

<a name="11"></a>
# 11. خطة البناء المرحلية (مربوطة ببوابات الاستراتيجية)

تُبنى بالبوابات لا بالتقويم. كل مرحلة تُفعّل أنظمة محدّدة فقط.

## المرحلة 0 — تحقق الرسالة (أسبوع 1-6، بالتوازي)
**الأنظمة:** 3 (Fingerprint أساسي) + 4 (URL Adapter فقط) + 5 (Eval أساسي) + 2 (Rule-Pack يدوي واحد: DE) + 8 (Dossier + Timeline) + 9 (Stripe).
**الهدف:** فحص 200 متجر + Dossier مدفوع. **البوابة:** ≥5 تقارير مدفوعة.
**مؤجّل:** كل شيء آخر.

## المرحلة 1 — MVP + أول 50-100 عميل (أسبوع 7-16)
**يُضاف:** 3 (بذر Theme Intelligence — أهم 20 ثيم Shopware/Woo) + 6 (AI Fix كنص) + 7 (KnowledgeEntry أساسي، بلا تدريب بعد) + 10 (Changelog يدوي).
**الطبقة القانونية:** حزمة DE مكتملة + بذر EU. `ComplianceProfile` بولاية واحدة.
**البوابة:** 50-100 عميل مدفوع + Churn مقبول.

## المرحلة 2 — الخندق والبقاء (بعد 100 عميل)
**يُضاف:** 1 (Legal Ingestion نصف-آلي كامل — Watcher + LLM + بوابة Curator) + Continuous Crawl (Flow C) + إعادة حساب آلية.
**الطبقة القانونية:** حزمة US كاملة → **تفعيل الدمج متعدد الولايات** (`combination_mode`). هنا يصبح المنتج دولياً.
**البوابة:** Churn ↓ / ARPU ↑.

## المرحلة 3 — التحقق البشري والقناة (توسّع)
**يُضاف:** بوابة Prüfstelle (Flow D) + حلقة الخبير تغذّي الخندق + White-Label للوكالات (Flow E) + مدخلات Theme/Plugin/Design System Adapters.
**البوابة:** أول Prüfstelle موقِّع + أول وكالة بمقاعد.

## المرحلة 4 — Enterprise + المنصّة
**يُضاف:** تدريب نماذج الخندق (كشف/توقّع) + GitHub Action/CI + Design System Analysis كامل + حِزم دول أوروبية فردية + (احتمالاً) منتج بيانات الـStack Census.

## ملخّص التتابع
```
P0: 3,4(url),5,2(DE يدوي),8,9        → أول يورو
P1: +Theme Intelligence,6,7(أساسي)   → 100 عميل
P2: +1(Legal كامل),US,دمج            → دولي + خندق
P3: +Prüfstelle,White-Label,adapters → قناة + بشري
P4: +تدريب,CI,Design System,EU-دول   → منصّة
```

---

## خاتمة

هذه الوثيقة تترجم كامل استراتيجية `KonformOS_Strategy_Journey.md` إلى نظام قابل للبناء عبر 10 أنظمة فرعية، بمحورين للـRouter (تقني + قانوني)، وقلبٍ هو الطبقة القانونية القابلة للإصدار (Rules-as-Data). القرارات الصعبة التراجع — نماذج البيانات، حدود الأنظمة، Compliance Profile Schema، سلامة الإثبات — محسومة هنا. الكود يُستخرَج منها لاحقاً.

**الخطوة التالية المنطقية:** توليد هيكل الكود الابتدائي (FastAPI project skeleton + Pydantic models + Alembic migrations) من نماذج البيانات والـSchema في هذه الوثيقة — في جلسة منفصلة، لأنه الآن قرار مُتَّخَذ لا تخمين.

*تخطيط هندسي واستراتيجي. القرارات القانونية (المسؤولية، الختم الزمني، DSGVO، UPL) تحتاج مراجعة كانزلاي مختص قبل الإنتاج.*
