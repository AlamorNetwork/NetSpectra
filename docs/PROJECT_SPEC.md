# Phoenix Protocol Research Lab (PPRL)
## سند مرجع پروژه — Project Specification

**نسخه:** 0.1.0  
**تاریخ مبنا:** 2026-10-30  
**مدت برنامه:** ۶ ماه / ۲۴ اسپرینت هفتگی (برنامه‌ریزی نسبی؛ نه تعهد زمانی)  
**وضعیت:** Proposal / Ready for Sprint 1  
**مجوز پیشنهادی:** Apache-2.0 برای کد؛ CC BY 4.0 برای اسناد؛ مجوز و شرایط مستقل برای داده‌ها  
**زبان‌ها:** مستندات فارسی + خلاصه فنی و README انگلیسی

---

## 1. چشم‌انداز
PPRL یک آزمایشگاه متن‌باز برای **اندازه‌گیری، بازتولید و تبیین رفتار پروتکل‌های شبکه در حضور محدودسازی و DPI** است. تمرکز روی تولید شواهد علمی، آزمایش‌های تکرارپذیر، ابزارهای تحلیل و انتشار نتایج دقیق است؛ نه پنل فروش VPN یا ادعای «عبور تضمینی» از فیلترینگ.

### اهداف قابل اندازه‌گیری
1. ساخت محیط آزمایشگاهی ایزوله که رفتار TCP/TLS/QUIC/HTTP/3 را اندازه بگیرد.
2. تبدیل مشاهده و قضاوت انسانی به آزمایش دارای شناسه، تنظیمات نسخه‌دار، داده خام، نتایج و بازاجرای خودکار.
3. جداکردن «اختلال شبکه» از «شواهد احتمالی محدودسازی»؛ عدم نسبت‌دادن قطعی بدون کنترل مناسب.
4. طراحی بنچمارک منصفانه برای هزینه، پایداری، کارایی و نرخ خطای تشخیص.
5. انتشار یک بسته پژوهشی قابل استناد: کد، روش‌شناسی، نسخه‌ها، گزارش و داده امن.

### معیار موفقیت پایان دوره (پیشنهادی)
- اجرای تکرارپذیر حداقل ۱۵ سناریوی آزمایشگاهی با سه تکرار برای هر سناریو.
- ثبت نسخه ابزارها، پیکربندی، seed و checksum مصنوعات در ۱۰۰٪ ران‌های منتشرشده.
- اجرای CI برای unit/integration و smoke test محیط آزمایش.
- مقایسه دست‌کم سه کلاس جریان مجاز و دو مکانیزم محدودسازی مصنوعی.
- تولید یک گزارش انگلیسی قابل بازبینی همراه با limitations و reproducibility appendix.
- حداقل یک انتشار عمومی با نسخه مشخص، changelog و دستور اجرای محلی.
این اعداد **هدف پروژه** هستند نه ادعای پیشاپیش درباره نتایج.

## 2. محدوده / خارج از محدوده
### داخل محدوده
- تحلیل passive و فعال فقط روی ترافیک تولیدشده توسط خود آزمایشگاه یا با رضایت صریح.
- PCAP، qlog، NetFlow-style summaries، متریک‌های TLS/QUIC و بررسی رفتار middlebox.
- شبیه‌سازی DNS interference، محدودیت UDP، افت بسته، jitter، delay، اختلال handshake در محیط کنترل‌شده.
- طبقه‌بندی ترافیک مصنوعی؛ سنجش false positive، leakage، drift و robustness.
- مرور و تحلیل روش‌های منتشرشده مقابله با DPI، ارزیابی اخلاقی و مقایسه آزمایشگاهی.
- داشبورد، API و exports با هویت‌زدایی و مدیریت سطح دسترسی.

### خارج از محدوده در نسخه 0.1
- اسکن اینترنت بدون رضایت یا حمله به تجهیزات اپراتورها.
- جمع‌آوری محتوای خصوصی یا TLS keys کاربران.
- استقرار خودکار روی شبکه‌های اشخاص ثالث یا راه‌اندازی سرویس عمومی ناشناس.
- نوشتن crypto اختصاصی برای استفاده عملیاتی، وعده bypass دائمی یا انتشار آسیب‌پذیری بدون ارزیابی مسئولانه.
- ادعای «ساخت پروتکل امن جدید» صرفاً با عبور از چند آزمون.

## 3. سوالات پژوهشی (Research Questions)
- **RQ1:** کدام ویژگی‌های قابل مشاهده بدون رمزگشایی محتوای برنامه برای تمایز جریان‌ها کافی‌اند؟
- **RQ2:** در چه شرایطی loss، MTU، NAT و UDP rate limiting علائم مشابه مسدودسازی عمدی تولید می‌کنند؟
- **RQ3:** نرخ خطای مثبت و منفی دسته‌های مختلف DPI در محیط آزمایشگاهی چگونه تغییر می‌کند؟
- **RQ4:** چگونه تغییرات شرایط شبکه و نسخه نرم‌افزار بر نتیجه بنچمارک اثر می‌گذارند؟
- **RQ5:** کدام مصالحه‌ها میان حریم خصوصی، سربار ترافیک، تأخیر و تحمل اختلال وجود دارند؟
- **RQ6:** کدام داده‌ها و متدولوژی برای بازتولید مستقل و انتشار بی‌خطر کافی است؟

## 4. مدل تهدید و محدودیت ادعا
| جزء | فرض اولیه | نتیجه برای پژوهش |
|---|---|---|
| ناظر غیرفعال | metadata، زمان و اندازه بسته را می‌بیند | فقط تحلیل داده‌های مشاهده‌پذیر |
| middlebox فعال در lab | می‌تواند block/drop/delay/rate-limit کند | آزمون در namespace ایزوله |
| ناظر دارای fingerprint آماری | الگوهای آماری جریان را تحلیل می‌کند | سنجش تعمیم و false positive |
| طرف مقابل نامطمئن | endpoint ممکن است خطا یا نسخه متفاوت داشته باشد | نگه‌داری نسخه و کنترل‌های آزمایش |
| شبکه واقعی | شرایط و سیاست نامعلوم و متغیر دارد | نتیجه محدود به دامنه داده؛ بدون نسبت‌دادن قطعی |

**نکته:** تشخیص DPI از روی یک trace تنها معمولاً قطعی نیست؛ نیاز به کنترل، تکرار، فرضیه جایگزین و درجه اطمینان داریم.

## 5. ماژول‌های محصول
### A. QUIC Observatory — ماه ۱
- Probeها و collector برای DNS/TCP/TLS/HTTP/3/QUIC در مقصدهای تحت کنترل.
- واردکردن PCAP/qlog؛ parser خطاها و استخراج بازه‌های زمانی و آمار.
- تشخیص سناریوهای رایج: قطع UDP، PMTU، handshake timeout، fallback، DNS failure.
- خروجی گزارش با بخش **Observed / Inferred / Unknown**.

### B. DPI-X — ماه ۲
- توپولوژی: client -> isolated middlebox -> server.
- سناریوهای rule-based برای SNI، ALPN، پروتکل و تصمیم‌های drop/delay/throttle فقط روی ترافیک lab.
- صفحه مقایسه baseline و intervention با controls و تکرارها.
- ثبت نسخه rule و امکان replay.

### C. FlowPrint — ماه ۳
- استخراج inter-arrival times، packet sizes، directionality، duration، flow counts، نسبت down/up و handshake features مجاز.
- dataset schema، train/test split مبتنی بر گروه برای جلوگیری از leakage.
- baseline آماری و مدل قابل توضیح؛ confusion matrix و calibration.
- مستندسازی محدودیت fingerprinting روی داده واقعی و drift.

### D. EvasionBench — ماه ۴
- چارچوب آزمایش برای مقایسه traffic-shapingهای ایمن و شبیه‌سازی محدودسازی در lab.
- معیارهای fairness، throughput، latency، jitter، overhead، reliability، detectability و false positives.
- خروجی نتیجه با confidence interval و تکرارهای کنترل‌شده.
- امکان تعریف سناریو از فایل declarative بدون استقرار خودکار روی شبکه عمومی.

### E. CensorAtlas — ماه ۵
- ingestion اختیاری برای داده‌های عمومی و داده‌هایی با رضایت.
- جداکردن observation از attribution؛ امتیاز کیفیت شاهد.
- مدل حفظ حریم خصوصی، aggregation threshold، کاهش دقت زمان/مکان، retention و حذف داده.
- API و نمودار شفاف با provenance؛ مقایسه بدون افشای IP اشخاص.

### F. Research Release — ماه ۶
- replication package و گزارش فنی انگلیسی با فارسی مکمل.
- threat model نهایی، ablation، failure analysis، independent review.
- release عمومی، road map بعدی، CONTRIBUTING و فرآیند disclosure.

## 6. معماری مرجع
```text
[CLI / Research UI]
       |
[FastAPI Control API] ---- [Auth & RBAC]
       |
[Experiment Orchestrator] ---- [Scenario Registry / Versioned YAML]
       |
+------+--------------------+--------------------+
| Traffic Generator        | Capture Adapter     | Lab Controller      |
| TCP/TLS/QUIC endpoints   | PCAP / qlog / logs  | namespaces / tc     |
+------+--------------------+--------------------+
       |
[Validation & Analysis Workers]
       |
[PostgreSQL metadata] + [local artifact store: PCAP/qlog/results]
       |
[Reports / CSV / JSON / static HTML]
```

### پیشنهاد فنی
- **زبان اصلی orchestration/analysis:** Python 3.12 یا 3.13 پایدار، با lockfile و CI؛ Python 3.15 فقط پس از سازگاری کتابخانه‌ها.
- **API:** FastAPI + Pydantic + SQLAlchemy + Alembic.
- **UI:** React + TypeScript؛ RTL برای فارسی؛ UI پس از صحت CLI و موتور آزمایش.
- **بسته‌ها:** Scapy، tshark/Wireshark، aioquic، pandas/Polars، scikit-learn.
- **آزمایشگاه:** Linux namespaces / veth / tc netem / Docker Compose در Linux یا WSL2؛ Windows میزبان برای توسعه.
- **داده:** PostgreSQL برای metadata؛ filesystem یا S3-compatible storage برای مصنوعات.
- **استاندارد کیفیت:** pytest، Ruff، mypy/pyright، pre-commit، GitHub Actions، SBOM و dependency scan.
- **امنیت:** رمززدایی محتوای واقعی ممنوع پیش‌فرض؛ secrets فقط env/key manager؛ least privilege؛ no PCAP upload by default.

### پیشنهاد ساختار مخزن
```text
pprl/
  README.md                 # English
  README.fa.md              # فارسی
  LICENSE
  SECURITY.md
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  .github/workflows/
  docs/
    PROJECT_SPEC.md
    ROADMAP_TODO.md
    ADR/
    methodology/
    research-notes/
  schemas/
    experiment.schema.json
    artifact-manifest.schema.json
    measurement.schema.json
  packages/
    pprl_core/
    pprl_capture/
    pprl_analysis/
  services/
    api/
    worker/
  clients/
    cli/
    web/
  lab/
    compose/
    namespaces/
    scenarios/
    endpoints/
  datasets/
    README.md               # نه داده خام حساس
    synthetic/
  experiments/
    templates/
  tests/
    unit/
    integration/
    e2e/
  reports/
    templates/
  scripts/
```

## 7. قرارداد داده و قابلیت بازتولید
### Experiment manifest (نمونه مفهومی)
```yaml
experiment_id: exp-0001
scenario: quic_udp_loss_baseline
scenario_version: 1
run_seed: 42
lab_mode: isolated
consent_scope: synthetic_only
protocol: quic
network_profile:
  latency_ms: 20
  packet_loss_pct: 0
  bandwidth_mbps: 100
repetitions: 3
artifacts:
  retain_raw_pcap: false
  retain_qlog: true
```
هر Run باید `run_id`، UTC timestamp، platform info، git SHA، نسخه ابزارها، hash فایل سناریو، وضعیت اجرا، مجموعه متریک‌ها، sample size، failure reason و hash مصنوعات داشته باشد.

### کلاس‌های نتیجه
- `observed`: مستقیم اندازه‌گیری شده.
- `derived`: با فرمول مشخص محاسبه شده.
- `hypothesis`: تفسیر با شواهد و کنترل ذکرشده.
- `unknown`: شواهد ناکافی.
نتایج نباید از `unknown` به «فیلتر شده» تبدیل شوند مگر کنترل و روش‌شناسی مناسب ثبت شود.

## 8. روش‌شناسی بنچمارک
1. تعریف فرضیه و primary endpoint **قبل از اجرا**.
2. ثبت baseline و کنترل منفی/مثبت در شبکه ایزوله.
3. نسخه‌بندی سناریو و استفاده از seed ثبت‌شده.
4. تکرار، randomization ترتیب آزمون و جلوگیری از warm-up bias.
5. گزارش n، میانگین، median، P95، انحراف/فاصله اطمینان، خطا و missing data.
6. عدم تغییر متریک اصلی بعد از مشاهده نتیجه بدون ذکر exploratory analysis.
7. جداسازی داده training/test با group split بر مبنای session/endpoint.
8. پذیرش نتایج منفی و انتشار موارد شکست نیز.

## 9. اخلاق، حریم خصوصی و عملیات
- اندازه‌گیری فعال بیرونی فقط روی endpoint متعلق به آزمایشگاه یا با مجوز صریح.
- رضایت آگاهانه برای مشارکت‌کننده؛ دکمه stop؛ حداقل جمع‌آوری.
- IP و شناسه‌های حساس را در داده عمومی منتشر نکنید؛ حذف/aggregation در سطح raw-to-public.
- انتشار PCAP خام به‌صورت پیش‌فرض ممنوع؛ dataset مصنوعی یا scrubbed با بازبینی.
- HTTPS، access control، audit trail، retention و deletion policy.
- برای اعتبار علمی از تفکیک فرضیه‌های متنافس و برچسب عدم قطعیت استفاده کنید.

## 10. Definition of Done سراسری
هر feature تنها هنگامی Done است که:
- design و acceptance criteria داشته باشد؛
- unit + integration tests مرتبط سبز باشند؛
- حداقل یک دستور demo مستند و قابل بازتولید داشته باشد؛
- خطاها، timeout و cancellation را مدیریت کند؛
- داده حساس لاگ نکند؛
- changelog / docs / threat considerations به‌روزرسانی شده باشد؛
- reviewer نتیجه را روی محیط clean تأیید کند.

## 11. مدیریت پروژه
- هر اسپرینت: یک issue epic، چند issue کوچک، milestone و demo.
- convention: `PPRL-M01-W01-T01`، وضعیت‌ها `TODO / IN_PROGRESS / BLOCKED / REVIEW / DONE`.
- شاخه‌ها: `main` محافظت‌شده، `feat/...`، `fix/...` و PR اجباری برای تغییرات حساس.
- ADR برای تصمیم‌های معماری؛ RFC کوتاه برای تغییر پروتکل یا روش‌شناسی.
- سه گیت: پایان ماه ۲ (lab معتبر)، ماه ۴ (مقایسه معتبر)، ماه ۶ (انتشار قابل استناد).

## 12. ریسک‌ها و جایگزین‌ها
| ریسک | اثر | کنترل |
|---|---|---|
| ناسازگاری ابزار با Windows | کندی توسعه | WSL2 Ubuntu / Linux CI؛ Python pinned |
| ادعای اشتباه درباره سانسور | آسیب اعتبار | controls + labeling + review |
| data leakage/PII | ریسک حریم خصوصی | synthetic-first + privacy review |
| overengineering UI | تأخیر علمی | CLI-first، UI در ماه‌های ۳ تا ۵ |
| benchmark bias | نتایج غیرقابل اعتماد | paired trials + randomized order |
| پیچیدگی پروتکل جدید | شکست امنیتی | فقط طرح پژوهشی و ارزیابی؛ no custom production crypto |
| وابستگی به measurement خارجی | missing data | import اختیاری و cache/replay |

## 13. منابع پایه رسمی
- QUIC Transport — RFC 9000: https://www.rfc-editor.org/rfc/rfc9000
- QUIC TLS — RFC 9001: https://www.rfc-editor.org/rfc/rfc9001
- HTTP/3 — RFC 9114: https://www.rfc-editor.org/rfc/rfc9114
- TLS 1.3 — RFC 8446: https://www.rfc-editor.org/rfc/rfc8446
- Proxying UDP in HTTP — RFC 9298: https://www.rfc-editor.org/rfc/rfc9298
- OONI: https://ooni.org/ and https://docs.ooni.org/
- Suricata: https://docs.suricata.io/
- qlog: https://www.ietf.org/ and https://github.com/quiclog
- Linux netem: https://man7.org/linux/man-pages/man8/tc-netem.8.html

## 14. نقطه شروع
**Sprint 1:** ایجاد repo، آزمایش Linux namespace، تولید اولین TCP/UDP echo flow، ثبت manifest، ذخیره متریک و انتشار اولین reproducible smoke test. فایل `ROADMAP_TODO.md` مرجع دقیق تمام کارهاست.
