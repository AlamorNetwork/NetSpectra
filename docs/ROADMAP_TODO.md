# PPRL — نقشه راه کامل و چک‌لیست اجرایی ۲۴ هفته‌ای

**نسخه:** 0.1.0 | **تاریخ:** 2026-10-30 | **وضعیت اولیه:** همه تسک‌ها TODO

> این برنامه ۲۴ اسپرینت نسبی دارد و پیش‌بینی قطعی زمان نیست. انتقال به هفته بعد فقط پس از قبولی گیت انجام شود. پروژه صرفاً برای محیط‌های آزمایشگاهی مجاز، endpointهای متعلق به خود پژوهش و داده رضایت‌محور طراحی شده است.

## روش استفاده
- هر checkbox یک Issue مستقل یا subtask؛ شناسه‌ها ثابت‌اند (`PPRL-M01-W01-T01`).
- حالت‌ها: `TODO`, `IN_PROGRESS`, `BLOCKED`, `REVIEW`, `DONE`.
- در پایان هر هفته: دستور اجرا، تست‌های سبز، فایل خروجی، نتیجه مشاهده‌شده و بدهی فنی را در `docs/weekly/Wxx.md` بنویس.
- هر کار Done باید evidence (log مصنوعی، تست، PR، report) و reviewer داشته باشد.
- کار با داده واقعی فقط بعد از privacy/consent gate مجاز است.

## Milestones و وابستگی‌های مهم
| ماه | ماژول | پیش‌نیاز | گیت اصلی |
|---|---|---|---|
| M01 | بنیان آزمایشگاه و QUIC Observatory | — | اجرای clean-room با PCAP/qlog و گزارش ریشه خطا |
| M02 | DPI-X و صحت‌سنجی مداخله | M01 | تطابق تصمیم DPI با رخداد واقعی و کنترل‌های مثبت/منفی |
| M03 | FlowPrint و سنجش fingerprint | M02 | مدل baseline به‌همراه uncertainty، confusion matrix و ارزیابی گروه‌بندی‌شده |
| M04 | EvasionBench و مقایسه منصفانه | M03 | گزارش تکرارپذیر comparative benchmark با CI و تحلیل خطا |
| M05 | CensorAtlas، شفافیت و حریم خصوصی | M04 | آزمایش ورود/حذف/انتشار داده با privacy gate |
| M06 | انتشار پژوهشی و سازوکار مشارکت | M05 | release همراه با بسته بازتولید، گزارش روش‌شناسی و roadmap بعدی |

## روال مشترک هر هفته (اجباری)
- [ ] جمع‌آوری issueها و ثبت scope/assumption و risk
- [ ] تعیین acceptance criteria و تست قبل از پیاده‌سازی
- [ ] اجرای test و CI و ثبت فرمان دقیق reproducibility
- [ ] ثبت artifact hashes، نسخه ابزارها و گزارش Observed/Derived/Hypothesis/Unknown
- [ ] code review، security/privacy review متناسب، به‌روزرسانی docs
- [ ] demo کوتاه، فهرست blockerها و تصمیم ادامه/بازنگری

## ماه ۱ — بنیان آزمایشگاه و QUIC Observatory
**هدف:** هدف: اولین اندازه‌گیری تکرارپذیر QUIC/TCP/TLS روی مقصدهای آزمایشگاهی  
**شرط خروج:** اجرای clean-room با PCAP/qlog و گزارش ریشه خطا

### هفته 1 (W01) — Workspace و قرارداد پایه
**خروجی هفته:** artefact `reports/w01/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M01-W01-T01** — ایجاد monorepo، README فارسی/انگلیسی، LICENSE و ساختار پوشه‌ها
- [ ] **PPRL-M01-W01-T02** — تعریف issue template، PR template، conventional commits و branch protection
- [ ] **PPRL-M01-W01-T03** — تنظیم Python pinned، uv/pip lock، Ruff، pytest و CI smoke
- [ ] **PPRL-M01-W01-T04** — ایجاد اولین JSON schema برای Experiment و Run؛ sample معتبر/نامعتبر
- [ ] **PPRL-M01-W01-T05** — راه‌اندازی WSL2/Linux و تست loopback TCP/UDP بدون ارسال به اینترنت
- [ ] **PPRL-M01-W01-T06** — ثبت ADR-001 درباره lab-only و خط‌مشی رضایت و داده حساس

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 2 (W02) — زیرساخت ثبت آزمایش
**خروجی هفته:** artefact `reports/w02/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M01-W02-T01** — پیاده‌سازی CLI برای create/list/run/inspect آزمایش
- [ ] **PPRL-M01-W02-T02** — تولید run_id، timestamps UTC، git SHA، environment metadata
- [ ] **PPRL-M01-W02-T03** — پیاده‌سازی artifact manifest، checksum و directory layout
- [ ] **PPRL-M01-W02-T04** — اجرای TCP echo و UDP echo روی دو endpoint تحت کنترل
- [ ] **PPRL-M01-W02-T05** — نوشتن timeout/retry/cancel و error taxonomy
- [ ] **PPRL-M01-W02-T06** — تست rerun با seed یکسان و خروجی قابل مقایسه

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 3 (W03) — Capture و instrumentation
**خروجی هفته:** artefact `reports/w03/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M01-W03-T01** — تعریف interface قابل تعویض CaptureAdapter
- [ ] **PPRL-M01-W03-T02** — پیاده‌سازی capture روی interface آزمایشگاهی با tshark/pcap
- [ ] **PPRL-M01-W03-T03** — ساخت parser برای basic 5-tuple، packet count و byte count
- [ ] **PPRL-M01-W03-T04** — ساخت exporter JSON/CSV و dataset synthetic example
- [ ] **PPRL-M01-W03-T05** — اضافه‌کردن redaction برای IP/token/secrets در log
- [ ] **PPRL-M01-W03-T06** — Integration test برای capture، checksum و fail-safe shutdown

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 4 (W04) — QUIC baseline
**خروجی هفته:** artefact `reports/w04/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M01-W04-T01** — راه‌اندازی client/server آزمایشی QUIC/HTTP3 با aioquic
- [ ] **PPRL-M01-W04-T02** — ثبت handshake duration، success/failure، retry و timeout
- [ ] **PPRL-M01-W04-T03** — راه‌اندازی qlog exporter و reader با تشخیص نسخه schema
- [ ] **PPRL-M01-W04-T04** — آزمایش TCP TLS و QUIC روی شرایط یکسان برای baseline
- [ ] **PPRL-M01-W04-T05** — ساخت report اولیه Observed/Derived/Hypothesis/Unknown
- [ ] **PPRL-M01-W04-T06** — گیت ماه ۱: نصب از صفر و اجرای ۳ run موفق و ۱ failure کنترل‌شده

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

#### Gate M01
- [ ] سناریوی demo به‌صورت end-to-end روی محیط clean اجرا شد.
- [ ] همه failureهای شناخته‌شده و محدودیت‌های نتایج مستند شد.
- [ ] نسخه اسناد، schemas و نتایج با tag داخلی ماه هماهنگ شد.
- [ ] موافقت برای ورود به مرحله بعد ثبت شد.

## ماه ۲ — DPI-X و صحت‌سنجی مداخله
**هدف:** هدف: بازتولید محدودسازی مصنوعی در middlebox کنترل‌شده  
**شرط خروج:** تطابق تصمیم DPI با رخداد واقعی و کنترل‌های مثبت/منفی

### هفته 5 (W05) — توپولوژی ایزوله
**خروجی هفته:** artefact `reports/w05/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M02-W05-T01** — ساخت topology با Linux namespaces و veth client/router/server
- [ ] **PPRL-M02-W05-T02** — قطع مسیر پیش‌فرض اینترنت lab و اثبات isolation
- [ ] **PPRL-M02-W05-T03** — تعیین allowlist مقصد و محدودسازی نرخ/حجم ترافیک
- [ ] **PPRL-M02-W05-T04** — ساخت provisioning/cleanup idempotent و teardown روی خطا
- [ ] **PPRL-M02-W05-T05** — نوشتن دیاگرام توپولوژی و دستور validation
- [ ] **PPRL-M02-W05-T06** — Integration test برای leakage و cleanup حتی پس از SIGINT

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 6 (W06) — موتور سناریو
**خروجی هفته:** artefact `reports/w06/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M02-W06-T01** — تعریف YAML schema برای impairment و match condition
- [ ] **PPRL-M02-W06-T02** — پیاده‌سازی registry و versioning سناریوها
- [ ] **PPRL-M02-W06-T03** — مدیریت tc netem برای delay/loss/jitter/rate در lab
- [ ] **PPRL-M02-W06-T04** — ثبت pre/post snapshots و rule lifecycle
- [ ] **PPRL-M02-W06-T05** — افزودن dry-run و fail-closed برای هر سناریو
- [ ] **PPRL-M02-W06-T06** — تست baseline در برابر intervention با تکرار

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 7 (W07) — شبیه‌ساز DPI
**خروجی هفته:** artefact `reports/w07/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M02-W07-T01** — تعریف rule engine آزمایشگاهی برای metadata مجاز مانند پروتکل/ALPN/SNI آزمایشی
- [ ] **PPRL-M02-W07-T02** — پیاده‌سازی actionهای log/drop/delay/throttle در مسیر ایزوله
- [ ] **PPRL-M02-W07-T03** — ثبت match reason، decision id و rule version
- [ ] **PPRL-M02-W07-T04** — ایجاد control مثبت و منفی برای هر rule
- [ ] **PPRL-M02-W07-T05** — آزمودن عدم اثرگذاری بر ترافیک خارج از scope
- [ ] **PPRL-M02-W07-T06** — تولید trace محرمانه و event summary قابل انتشار

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 8 (W08) — اعتبارسنجی و گزارش DPI
**خروجی هفته:** artefact `reports/w08/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M02-W08-T01** — پیاده‌سازی همبستگی eventهای middlebox با client/server capture
- [ ] **PPRL-M02-W08-T02** — ساخت report علت‌های جایگزین (MTU/DNS/rate) برای هر شکست
- [ ] **PPRL-M02-W08-T03** — ارزیابی precision تشخیص intervention در نمونه مصنوعی
- [ ] **PPRL-M02-W08-T04** — نوشتن limitation و failure-case catalog
- [ ] **PPRL-M02-W08-T05** — سخت‌سازی cleanup، permissions، CI lab smoke
- [ ] **PPRL-M02-W08-T06** — گیت ماه ۲: حداقل ۶ سناریوی replayable با کنترل و نشانه قابل ممیزی

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

#### Gate M02
- [ ] سناریوی demo به‌صورت end-to-end روی محیط clean اجرا شد.
- [ ] همه failureهای شناخته‌شده و محدودیت‌های نتایج مستند شد.
- [ ] نسخه اسناد، schemas و نتایج با tag داخلی ماه هماهنگ شد.
- [ ] موافقت برای ورود به مرحله بعد ثبت شد.

## ماه ۳ — FlowPrint و سنجش fingerprint
**هدف:** هدف: طبقه‌بندی آماری بر اساس داده مصنوعی بدون نشت داده  
**شرط خروج:** مدل baseline به‌همراه uncertainty، confusion matrix و ارزیابی گروه‌بندی‌شده

### هفته 9 (W09) — قرارداد دیتاست
**خروجی هفته:** artefact `reports/w09/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M03-W09-T01** — تعریف schema flow و label provenance و measurement quality
- [ ] **PPRL-M03-W09-T02** — تولید جریان‌های مصنوعی با توزیع اندازه و زمان متنوع
- [ ] **PPRL-M03-W09-T03** — ثبت اطلاعات session و endpoint برای split گروهی
- [ ] **PPRL-M03-W09-T04** — تعریف policy برای حذف payload و شناسه حساس
- [ ] **PPRL-M03-W09-T05** — نوشتن validation و checksum dataset
- [ ] **PPRL-M03-W09-T06** — نسخه‌بندی snapshot دیتاست و data dictionary

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 10 (W10) — Feature extraction
**خروجی هفته:** artefact `reports/w10/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M03-W10-T01** — پیاده‌سازی packet direction و length histogram
- [ ] **PPRL-M03-W10-T02** — محاسبه inter-arrival، burst، duration و rates
- [ ] **PPRL-M03-W10-T03** — ثبت missing / truncated capture و confidence flags
- [ ] **PPRL-M03-W10-T04** — تست ویژگی‌ها روی PCAP کوچک با خروجی قابل انتظار
- [ ] **PPRL-M03-W10-T05** — ساخت CLI extract و export Parquet/CSV
- [ ] **PPRL-M03-W10-T06** — بنچمارک حافظه و زمان پردازش روی فایل متوسط

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 11 (W11) — Baseline classification
**خروجی هفته:** artefact `reports/w11/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M03-W11-T01** — تعریف فرضیه، target و metric قبل از آموزش
- [ ] **PPRL-M03-W11-T02** — ایجاد train/validation/test گروه‌بندی‌شده و leakage guard
- [ ] **PPRL-M03-W11-T03** — آموزش baseline ساده و مدل درختی قابل توضیح
- [ ] **PPRL-M03-W11-T04** — مقایسه با majority/random baseline
- [ ] **PPRL-M03-W11-T05** — گزارش confusion matrix، precision، recall، F1 و calibration
- [ ] **PPRL-M03-W11-T06** — ثبت model card و نسخه seed/features

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 12 (W12) — Robustness و reproducibility
**خروجی هفته:** artefact `reports/w12/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M03-W12-T01** — آزمایش روی شبکه با loss و latency متفاوت از آموزش
- [ ] **PPRL-M03-W12-T02** — ارزیابی sensitivity به endpoint و session جدید
- [ ] **PPRL-M03-W12-T03** — محاسبه bootstrap confidence interval برای metrics
- [ ] **PPRL-M03-W12-T04** — ساخت error analysis برای false positive/negative
- [ ] **PPRL-M03-W12-T05** — تولید report و notebook بازتولیدپذیر
- [ ] **PPRL-M03-W12-T06** — گیت ماه ۳: اجرای کامل pipeline از dataset تا report روی clean install

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

#### Gate M03
- [ ] سناریوی demo به‌صورت end-to-end روی محیط clean اجرا شد.
- [ ] همه failureهای شناخته‌شده و محدودیت‌های نتایج مستند شد.
- [ ] نسخه اسناد، schemas و نتایج با tag داخلی ماه هماهنگ شد.
- [ ] موافقت برای ورود به مرحله بعد ثبت شد.

## ماه ۴ — EvasionBench و مقایسه منصفانه
**هدف:** هدف: مقایسه کنترل‌شده تنظیمات و رفتارهای انتقال در برابر محدودسازی شبیه‌سازی‌شده  
**شرط خروج:** گزارش تکرارپذیر comparative benchmark با CI و تحلیل خطا

### هفته 13 (W13) — Protocol measurement matrix
**خروجی هفته:** artefact `reports/w13/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M04-W13-T01** — تعریف ماتریس TCP/TLS/QUIC و HTTP3 با نسخه مشخص
- [ ] **PPRL-M04-W13-T02** — انتخاب متریک‌های اولیه throughput/RTT/P95/jitter/reliability
- [ ] **PPRL-M04-W13-T03** — تعریف workloadهای کوچک/متوسط/بزرگ مصنوعی
- [ ] **PPRL-M04-W13-T04** — اجرای baseline paired و ثبت warm-up effects
- [ ] **PPRL-M04-W13-T05** — تعیین زمان‌بندی، stopping rule و random order
- [ ] **PPRL-M04-W13-T06** — تولید جدول هزینه CPU/memory/bytes transferred

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 14 (W14) — Benchmark orchestrator
**خروجی هفته:** artefact `reports/w14/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M04-W14-T01** — ساخت configuration schema برای trial و randomized schedules
- [ ] **PPRL-M04-W14-T02** — پیاده‌سازی اجرای batch با isolation و cleanup
- [ ] **PPRL-M04-W14-T03** — ثبت artifact lineage هر trial و نتایج failure
- [ ] **PPRL-M04-W14-T04** — تعریف replay کامل و resume امن پس از قطع
- [ ] **PPRL-M04-W14-T05** — ساخت dashboard ساده progress بدون ادعای نتیجه
- [ ] **PPRL-M04-W14-T06** — Integration test برای partial runs و cancellation

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 15 (W15) — Resilience experiments
**خروجی هفته:** artefact `reports/w15/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M04-W15-T01** — طراحی چند سیاست انتقال آزمایشی و traffic shaping در lab
- [ ] **PPRL-M04-W15-T02** — مقایسه اثر rate limit و UDP loss بدون تغییر همزمان چند متغیر
- [ ] **PPRL-M04-W15-T03** — بررسی تحمل NAT rebinding/MTU تحت کنترل آزمایشگاه
- [ ] **PPRL-M04-W15-T04** — ثبت سربار bytes/CPU و تأخیر به جای فقط success
- [ ] **PPRL-M04-W15-T05** — ارزیابی خروجی classifier در هر شرایط آزمایشگاهی
- [ ] **PPRL-M04-W15-T06** — ثبت tradeoffها و نبود تضمین تعمیم به اینترنت واقعی

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 16 (W16) — تحلیل منصفانه
**خروجی هفته:** artefact `reports/w16/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M04-W16-T01** — اجرای تکرارها با ترتیب تصادفی و seeds ثبت‌شده
- [ ] **PPRL-M04-W16-T02** — ساخت paired plots، interval و uncertainty appendix
- [ ] **PPRL-M04-W16-T03** — تحلیل موارد شکست و biasهای آشکار
- [ ] **PPRL-M04-W16-T04** — بازبینی independent checklist بر روش‌شناسی
- [ ] **PPRL-M04-W16-T05** — به‌روزرسانی reproducibility pack و benchmark specification
- [ ] **PPRL-M04-W16-T06** — گیت ماه ۴: گزارش مقایسه با امکان تکرار نتایج در ماشین مستقل

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

#### Gate M04
- [ ] سناریوی demo به‌صورت end-to-end روی محیط clean اجرا شد.
- [ ] همه failureهای شناخته‌شده و محدودیت‌های نتایج مستند شد.
- [ ] نسخه اسناد، schemas و نتایج با tag داخلی ماه هماهنگ شد.
- [ ] موافقت برای ورود به مرحله بعد ثبت شد.

## ماه ۵ — CensorAtlas، شفافیت و حریم خصوصی
**هدف:** هدف: داشبورد و API نتایج با provenance و محافظت داده  
**شرط خروج:** آزمایش ورود/حذف/انتشار داده با privacy gate

### هفته 17 (W17) — منابع و provenance
**خروجی هفته:** artefact `reports/w17/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M05-W17-T01** — تعریف source registry برای synthetic، public و consented
- [ ] **PPRL-M05-W17-T02** — ساخت ingest pipeline با validation، dedupe و provenance
- [ ] **PPRL-M05-W17-T03** — بررسی مجوز و شرایط بازنشر هر داده عمومی
- [ ] **PPRL-M05-W17-T04** — تعریف confidence و evidence quality برای observation
- [ ] **PPRL-M05-W17-T05** — تست versioning schema و handling incomplete fields
- [ ] **PPRL-M05-W17-T06** — ثبت منبع و تاریخ snapshot به‌جای ادعای real-time

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 18 (W18) — Privacy by design
**خروجی هفته:** artefact `reports/w18/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M05-W18-T01** — تعریف consent record، retention و حذف داده
- [ ] **PPRL-M05-W18-T02** — پوشاندن/حذف IP، domain حساس، device IDs و payload
- [ ] **PPRL-M05-W18-T03** — ساخت privacy audit قبل از publish dataset
- [ ] **PPRL-M05-W18-T04** — سنجش re-identification risk و حداقل aggregation threshold
- [ ] **PPRL-M05-W18-T05** — تعریف دسترسی RBAC researcher/admin/public
- [ ] **PPRL-M05-W18-T06** — تست حذف داده و عدم باقی‌ماندن آن در export عمومی

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 19 (W19) — API و جستجوی نتایج
**خروجی هفته:** artefact `reports/w19/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M05-W19-T01** — طراحی endpoint نسخه‌دار /api/v1/experiments و /measurements
- [ ] **PPRL-M05-W19-T02** — فیلتر کیفیت، زمان، سناریو و protocol بدون raw PII
- [ ] **PPRL-M05-W19-T03** — افزودن pagination، rate limiting و response validation
- [ ] **PPRL-M05-W19-T04** — ایجاد OpenAPI و نمونه درخواست‌ها
- [ ] **PPRL-M05-W19-T05** — نوشتن integration tests برای auth/permissions
- [ ] **PPRL-M05-W19-T06** — راه‌اندازی محلی با PostgreSQL و migration نسخه‌دار

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 20 (W20) — داشبورد پژوهشی
**خروجی هفته:** artefact `reports/w20/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M05-W20-T01** — ساخت صفحه overview، سناریو، trial، comparisons و provenance
- [ ] **PPRL-M05-W20-T02** — نمایش uncertainty و علامت data insufficient در UI
- [ ] **PPRL-M05-W20-T03** — ساخت charts برای latency/loss/throughput و sample counts
- [ ] **PPRL-M05-W20-T04** — پشتیبانی RTL فارسی و انگلیسی
- [ ] **PPRL-M05-W20-T05** — اجتناب از نمایش location دقیق یا IP خام در نمای عمومی
- [ ] **PPRL-M05-W20-T06** — گیت ماه ۵: privacy review، demo dashboard و export امن

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

#### Gate M05
- [ ] سناریوی demo به‌صورت end-to-end روی محیط clean اجرا شد.
- [ ] همه failureهای شناخته‌شده و محدودیت‌های نتایج مستند شد.
- [ ] نسخه اسناد، schemas و نتایج با tag داخلی ماه هماهنگ شد.
- [ ] موافقت برای ورود به مرحله بعد ثبت شد.

## ماه ۶ — انتشار پژوهشی و سازوکار مشارکت
**هدف:** هدف: نسخه عمومی آزمایشگاه و گزارش پژوهشی قابل بازبینی  
**شرط خروج:** release همراه با بسته بازتولید، گزارش روش‌شناسی و roadmap بعدی

### هفته 21 (W21) — ثبت مقاله و نتایج
**خروجی هفته:** artefact `reports/w21/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M06-W21-T01** — انتخاب سؤال پژوهشی مشخص بر اساس نتایج واقعی
- [ ] **PPRL-M06-W21-T02** — ثبت outline مقاله: intro، related work، methods، results، limitations
- [ ] **PPRL-M06-W21-T03** — جمع‌آوری related work با ارجاع رسمی و تاریخ دسترسی
- [ ] **PPRL-M06-W21-T04** — ساخت figure/table scripts از داده واقعی
- [ ] **PPRL-M06-W21-T05** — فهرست فرضیه‌ها و alternative explanations
- [ ] **PPRL-M06-W21-T06** — نوشتن abstract بدون ادعای خارج از داده

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 22 (W22) — بازبینی علمی و امنیتی
**خروجی هفته:** artefact `reports/w22/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M06-W22-T01** — اجرای replication از صفر روی محیط جداگانه
- [ ] **PPRL-M06-W22-T02** — مرور threat model و negative controls
- [ ] **PPRL-M06-W22-T03** — security review برای CLI، API، dependencies و secrets
- [ ] **PPRL-M06-W22-T04** — privacy review برای تمام artifacts قابل انتشار
- [ ] **PPRL-M06-W22-T05** — مرور آماری و بازتولید confidence interval
- [ ] **PPRL-M06-W22-T06** — اصلاح نقص‌های blocking و ثبت known limitations

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 23 (W23) — بسته انتشار
**خروجی هفته:** artefact `reports/w23/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M06-W23-T01** — نهایی‌کردن installation docs، quickstart و troubleshooting
- [ ] **PPRL-M06-W23-T02** — ایجاد release artifacts و SBOM و signed checksums در صورت امکان
- [ ] **PPRL-M06-W23-T03** — به‌روزرسانی README، CONTRIBUTING، SECURITY و CODE_OF_CONDUCT
- [ ] **PPRL-M06-W23-T04** — آماده‌کردن dataset synthetic و sample reports
- [ ] **PPRL-M06-W23-T05** — افزودن CI matrix لینوکس و documentation build
- [ ] **PPRL-M06-W23-T06** — ساخت demo و changelog نسخه 0.1

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

### هفته 24 (W24) — انتشار و نقشه بعدی
**خروجی هفته:** artefact `reports/w24/` + تست و راهنمای اجرای مرتبط.

- [ ] **PPRL-M06-W24-T01** — انتشار GitHub release و نسخه‌گذاری tags
- [ ] **PPRL-M06-W24-T02** — انتشار گزارش فنی انگلیسی و خلاصه فارسی
- [ ] **PPRL-M06-W24-T03** — ارائه benchmark methodology و reproduction command
- [ ] **PPRL-M06-W24-T04** — بازکردن issues مشارکت و good-first-issueها
- [ ] **PPRL-M06-W24-T05** — ثبت metricهای واقعی استفاده/بازخورد بدون جمع‌آوری مخفی
- [ ] **PPRL-M06-W24-T06** — گیت ماه ۶: demo مستقل، paper، artifact package و فهرست پرسش‌های باز

**معیار پذیرش:** همه تسک‌های بالا دارای شاهد اجرایی باشند؛ داده محرمانه در commit نباشد؛ CI مرتبط سبز باشد؛ یک نفر غیر از نویسنده بتواند دستور README را اجرا کند.

#### Gate M06
- [ ] سناریوی demo به‌صورت end-to-end روی محیط clean اجرا شد.
- [ ] همه failureهای شناخته‌شده و محدودیت‌های نتایج مستند شد.
- [ ] نسخه اسناد، schemas و نتایج با tag داخلی ماه هماهنگ شد.
- [ ] موافقت برای ورود به مرحله بعد ثبت شد.

## اولویت‌بندی در صورت محدودیت زمان
1. **P0:** صحت اندازه‌گیری، isolation، تست، provenance و privacy؛ هیچ‌وقت حذف نشوند.
2. **P1:** CLI، metrics، reports و core pipeline.
3. **P2:** UI پیشرفته، live animation، پلاگین‌ها و اتوماسیون غیرضروری.

## مسیر بحرانی
`W01 → W02 → W03 → W04 → W05 → W06 → W07 → W08 → W09 → W10 → W11 → W12 → W13 → W14 → W15 → W16 → W17 → W18 → W19 → W20 → W21 → W22 → W23 → W24`

## تعریف یک گزارش هفتگی
```markdown
# Weekly Report Wxx
- Goal:
- Completed issue IDs:
- Commands to reproduce:
- Environment / tool versions:
- Data provenance and privacy scope:
- Observed outcomes:
- Uncertainties and alternative explanations:
- Tests passed / failed:
- Artifact SHA256:
- Blockers:
- Next-week decision:
```

## اولین دستور برای Codex
```text
Read docs/PROJECT_SPEC.md and docs/ROADMAP_TODO.md fully.
Implement only PPRL-M01-W01-T01 through T03 in this iteration.
Before coding: list files to modify, assumptions, and risks.
After coding: run unit tests/lint, report exact commands and outputs.
Do not implement later sprints, collect external user traffic, or access endpoints outside lab scope.
```

## ثبت پیشرفت
| شناسه | تاریخ شروع | وضعیت | PR / Commit | شاهد تست | blocker |
|---|---|---|---|---|---|
| W01 | — | TODO | — | — | — |

## وضعیت اجرای محلی — 2026-10-31

| شناسه | وضعیت | شاهد / مانع |
|---|---|---|
| PPRL-M01-W01-T01 | REVIEW | ساختار و README و LICENSE؛ تست نصب و build محلی موفق؛ بازبینی مستقل مانده |
| PPRL-M01-W01-T02 | BLOCKED | قالب‌ها و قواعد آماده؛ مخزن GitHub متصل است؛ branch protection هنوز اعمال نشده |
| PPRL-M01-W01-T03 | REVIEW | دریافت و نصب عادی با uv sync --locked موفق؛ Ruff و قالب‌بندی و ۱ تست پاس؛ بازبینی مستقل و CI میزبانی‌شده مانده |
| PPRL-M01-W01-T04 | REVIEW | دو JSON Schema و نمونه‌های مصنوعی معتبر/نامعتبر؛ تست اعتبارسنجی محلی؛ بازبینی مستقل مانده |
| PPRL-M01-W01-T05 | REVIEW | نصب و ۷۶ تست روی سرور Ubuntu 24 موفق؛ TCP/UDP هرکدام ۲۶ بایت؛ WSL محلی فعلاً لازم نیست؛ بازبینی انسانی مانده |
| PPRL-M01-W01-T06 | REVIEW | ADR-001 درباره lab-only و رضایت و داده حساس ثبت شد؛ بازبینی مستقل مانده |

جزئیات: `weekly/W01.md` و `../reports/w01/README.md`. موارد بالا هنوز Done نیستند.
