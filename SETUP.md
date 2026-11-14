# راه‌اندازی قدم‌به‌قدم

## ۰) نام صفحهٔ اصلی (مهم)
GitHub Pages فقط فایلی با نام **`index.html`** را در آدرس اصلی سایت نشان می‌دهد. اگر فایل در مخزن `dops_scanner_v14.html` نام دارد، آدرس
`https://alireza786786.github.io/dops_ip_scanner/` خطای ۴۰۴ می‌دهد (و سرویس‌ورکر هم نصب نمی‌شود، چون `index.html` را کش می‌کند).
راه‌حل: روی فایل بزنید ← آیکون مداد ← اسم فایل را به `index.html` تغییر دهید ← Commit. (یا فایل `index.html` همین بسته را آپلود کنید و نام قدیمی را حذف کنید.)

## ۱) فایل‌ها را روی مخزن بگذارید
1. وارد مخزن `dops_ip_scanner` شوید (روی گوشی: منوی مرورگر ← «نسخهٔ دسکتاپ»).
2. **Add file ← Upload files** را بزنید و محتوای این پوشه را آپلود کنید: `index.html`، `sw.js`، `manifest.json`، سه فایل `icon-*.png` (از جمله `icon-512-maskable.png`)، همهٔ `*.py`، پوشهٔ `tests/` و `.gitignore`.
3. فایل‌های داخل `.github/workflows/` را جدا آپلود کنید (در گیت‌هاب «Add file ← Create new file» و نام `.github/workflows/scanner.yml` را بنویسید و محتوا را بچسبانید، یا از کامپیوتر پوشه را بکشید و رها کنید). فایل قدیمی workflow را با `scanner.yml` جدید **جایگزین** کنید و `ci.yml` را اضافه کنید.
4. **Commit changes** را بزنید.

## ۲) Secrets
**Settings ← Secrets and variables ← Actions ← New repository secret**
- `BOT_TOKEN`: توکن ربات
- `CHAT_ID`: آیدی کانال (مثل `@Goodbaye_filtering`)
- `ADMIN_CHAT_ID` (**اختیاری**؛ اگر Worker را هم راه انداختید، همان مقدار را در Worker نیز بگذارید): آیدی چت خصوصی خودتان با ربات (اول به ربات `/start` بزنید) برای هشدار سلامت: «اسکن خراب است» (حداکثر هر ۶ ساعت) و «اسکن دوباره کار می‌کند» (بعد از بیش از ۶ ساعت وقفه). اگر نگذارید، هشداری ارسال نمی‌شود. توجه: اگر خود گیت‌هاب اصلاً اجرا نکند، هشدار هم نمی‌آید؛ برای آن نشان تازگی در صفحه و ماشهٔ بیرونی هست.

## ۳) دسترسی Actions
**Settings ← Actions ← General ← Workflow permissions** را روی **Read and write permissions** بگذارید و ذخیره کنید.

## ۴) اولین اجرا و ساخت شاخهٔ `data`
شاخهٔ `data` را **دستی نسازید**؛ خود workflow در اولین اجرا آن را می‌سازد.
1. تب **Actions ← Auto CDN Scanner & Telegram Sender ← Run workflow**
2. گزینهٔ **force_telegram** را تیک بزنید و **Run workflow** را بزنید (حدود ۲ تا ۴ دقیقه).
3. در لاگ ببینید: `usable (… verified)`؛ اگر verified صفر بود، مرحلهٔ تأیید HTTP از Actions بسته است (به من بگویید).
4. در صفحهٔ مخزن، منوی شاخه‌ها را باز کنید؛ باید شاخهٔ **`data`** با پوشهٔ `outputs/` را ببینید.
5. لینک زیر را باز کنید و یک فایل آی‌پی ببینید:
   `https://raw.githubusercontent.com/alireza786786/dops_ip_scanner/data/outputs/alive_cloudflare.txt`

> اگر مرحلهٔ ۴ شاخهٔ `data` را نشان نداد، لاگ مرحلهٔ **Publish outputs to data branch** را بفرستید.

## ۵) GitHub Pages
**Settings ← Pages**: منبع همان شاخهٔ `main` و پوشهٔ `/ (root)` بماند. بعد از یکی دو دقیقه صفحه را باز کنید؛ بالای صفحه «DOPS V15.0 · MERIDIAN» را باید ببینید. اگر نسخهٔ قدیمی آمد، چند بار رفرش کنید.

## ۶) پوشهٔ `outputs/` قدیمی
روی `main` دیگر استفاده نمی‌شود. **بعد از اینکه** مرحلهٔ ۴ و ۵ را دیدید، می‌توانید آن را حذف کنید (روی پوشه ← سه‌نقطه ← Delete directory). قبل از آن حذفش نکنید.

## ۷) Release
**Releases ← Create a new release**: تگ `v15.0`، عنوان و توضیحات را از `RELEASE_NOTES.md` بردارید، فایل zip را در Attach binaries بگذارید و **Publish release** را بزنید.

## ۸) کادر About
چرخ‌دندهٔ کنار About: توضیح کوتاه، آدرس سایت و تاپیک‌ها را از پایین `RELEASE_NOTES.md` بردارید.

## اجرای خودکار (هر ۳۰ دقیقه) انجام نمی‌شود
اجرای دستی کار می‌کند ولی زمان‌بندی نه؟ به این ترتیب بررسی کنید:
1. تب **Actions** ← از ستون چپ workflow «Auto CDN Scanner & Telegram Sender» را باز کنید. اگر بالای صفحه نوشته شده workflow غیرفعال است، **Enable workflow** را بزنید.
2. در لیست اجراها ستون **Event** را ببینید: ردیف‌های `schedule` باید حدود دقیقهٔ ۷، ۲۲، ۳۷ و ۵۲ هر ساعت دیده شوند (بعضی «اسکن را رد کرد» می‌نویسند و این عادی است). اگر ردیف قرمز (شکست‌خورده) هست، واردش شوید و خطا را بفرستید.
3. **Settings ← Actions ← General**: گزینهٔ «Allow all actions and reusable workflows» فعال باشد.
4. فایل workflow باید در شاخهٔ پیش‌فرض (`main`) و مسیر `.github/workflows/` باشد. بعد از هر ویرایش، اولین اجرای زمان‌بندی در نوبت بعدی (دقیقهٔ ۷ یا ۳۷) شروع می‌شود، نه فوراً.
5. **زمان‌بندی گیت‌هاب «بهترین تلاش» است:** بنا بر مستندات خودش، زمان‌بندی‌ها در ساعات پرترافیک (به‌خصوص ابتدای هر ساعت) دیر اجرا می‌شوند و بعضی نوبت‌ها ممکن است حذف شوند. چند نوبت جاافتاده عادی است؛ اگر **چند ساعت** هیچ اجرای `schedule` نبود، مشکل واقعی است.
6. در مخازن عمومی، اگر ۶۰ روز هیچ فعالیتی نباشد زمان‌بندی خودکار غیرفعال می‌شود (دکمهٔ Enable workflow).
7. نکته: اسکنر وب سن لیست مخزن را نشان می‌دهد؛ پس حتی اگر نوبتی جا بیفتد، کاربر کهنگی را می‌بیند.

اگر بعد از ۲ ساعت هنوز هیچ اجرای `schedule` ندیدید، **اسکرین‌شات تب Actions** و متن `scanner.yml` مخزن را بفرستید.

## Cloudflare Worker (اختیاری ولی پیشنهادی): اجرای ۳۰ دقیقه‌ای مطمئن + هشدار کهنگی + نتایج جمعی

گزارش شما نشان داد زمان‌بندی داخلی گیت‌هاب منظم نیست. این Worker (رایگان، روی حساب Cloudflare خودتان) آن را دور می‌زند.

**۱) ساخت Worker**
1. وارد `dash.cloudflare.com` شوید (یا ثبت‌نام رایگان کنید) ← از منو **Workers & Pages ← Create ← Create Worker**.
2. یک نام بدهید (مثلاً `dops-worker`) ← **Deploy**.
3. **Edit code** را بزنید و کل محتوای `worker/index.js` همین بسته را جایگزین کد پیش‌فرض کنید ← **Deploy**.
4. آدرسی مثل `https://dops-worker.<شما>.workers.dev` می‌گیرید؛ آن را نگه دارید.

**۲) متغیرها و رازها** (در صفحهٔ Worker: **Settings ← Variables and Secrets**)
| نام | نوع | مقدار |
|---|---|---|
| `GH_REPO` | متن | `alireza786786/dops_ip_scanner` |
| `GH_WORKFLOW` | متن | `scanner.yml` |
| `GH_REF` | متن | `main` |
| `ALLOWED_ORIGIN` | متن | `https://alireza786786.github.io` |
| `GH_TOKEN` | **راز (Secret)** | توکن fine-grained با دسترسی `Actions: Read and write` فقط روی همین مخزن (مثل بخش ماشهٔ بیرونی پایین) |
| `SALT` | **راز** | یک متن تصادفی طولانی دلخواه (فقط برای درهم‌سازی شناسهٔ گزارش‌دهنده‌ها) |
| `BOT_TOKEN` | **راز** (اختیاری) | همان توکن ربات تلگرام، برای هشدار کهنگی |
| `ADMIN_CHAT_ID` | **راز** (اختیاری) | آیدی چت خصوصی شما با ربات |

**۳) حافظهٔ KV** (برای نتایج جمعی؛ اگر نمی‌خواهید این بخش را رد کنید)
**Workers & Pages ← KV ← Create namespace** (مثلاً `dops-kv`) ← در صفحهٔ Worker **Settings ← Bindings ← Add ← KV Namespace**: Variable name = `KV`، namespace = همان.

**۴) زمان‌بندی (Cron Trigger)**
**Settings ← Triggers ← Cron Triggers ← Add Cron Trigger** ← `*/30 * * * *` ← Save.

**۵) تست**
در صفحهٔ Worker، تب Logs را باز کنید و چند دقیقه صبر کنید، یا آدرس `.../health` را در مرورگر باز کنید؛ باید `{"ok":true,...}` ببینید.

**۶) فعال‌کردن نتایج جمعی در خود اسکنر (اختیاری)**
در `index.html`، خط `const COMMUNITY_URL = '';` را به آدرس Workerتان تغییر دهید (مثلاً `'https://dops-worker.شما.workers.dev'`) و آپلود کنید. تا این خط خالی باشد، گزینهٔ «جمعی» و تیک اشتراک‌گذاری در پنل حریم خصوصی غیرفعال می‌مانند.

**نکات امنیتی:** `GH_TOKEN` فقط دسترسی اجرای workflow همین مخزن را دارد. حافظهٔ KV هرگز آی‌پی گزارش‌دهنده، کانفیگ یا توکن را نگه نمی‌دارد؛ فقط نام اپراتور (نرمال‌شده)، چند آی‌پی کلودفلر با پینگ، و یک شناسهٔ نصب درهم‌شده با `SALT` — همه حداکثر ۲۴ تا ۴۸ ساعت.

## اگر زمان‌بندی گیت‌هاب هنوز اجرا نمی‌شود: ماشهٔ بیرونی دستی (بدون Worker)
زمان‌بندی داخلی گیت‌هاب «بهترین تلاش» است. راه مطمئن‌تر این است که یک سرویس رایگان (مثل cron-job.org) هر ۳۰ دقیقه workflow را از بیرون **راه بیندازد**. اجرای راه‌افتاده از این طریق مثل «Run workflow» دستی است.

**۱) ساخت توکن (فقط برای همین مخزن)**
1. گیت‌هاب ← عکس پروفایل ← **Settings ← Developer settings ← Personal access tokens ← Fine-grained tokens ← Generate new token**
2. **Repository access**: Only select repositories ← `dops_ip_scanner`
3. **Repository permissions ← Actions: Read and write** (بقیه را دست نزنید)
4. **Expiration**: مثلاً ۹۰ روز (بعد از آن باید تمدید کنید)
5. توکن را همان لحظه کپی کنید (بعداً نشان داده نمی‌شود).

**۲) ساخت کار در cron-job.org**
- **URL:** `https://api.github.com/repos/alireza786786/dops_ip_scanner/actions/workflows/scanner.yml/dispatches`
- **Method:** POST
- **Schedule:** هر ۳۰ دقیقه
- **Headers:**
  - `Accept: application/vnd.github+json`
  - `Authorization: Bearer <توکن>`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `User-Agent: dops-scanner`
- **Body (JSON):** `{"ref":"main"}`
- نتیجهٔ موفق: کد **204**. در تب Actions اجرا با برچسب `workflow_dispatch` دیده می‌شود.

**نکات امنیتی:** توکن فقط اجازهٔ اجرای workflowهای همین مخزن را دارد. آن را فقط داخل سرویس cron بگذارید، جایی منتشر نکنید و اگر لو رفت از همان صفحهٔ گیت‌هاب **Revoke** کنید. اجرای دستی/بیرونی همیشه اسکن می‌کند و ارسال تلگرام همچنان هر ≈۳ ساعت است.

## اگر چیزی کار نکرد
| نشانه | علت محتمل |
|---|---|
| اجرای workflow قرمز و «push failed» | مرحلهٔ ۳ (Read and write) انجام نشده |
| تلگرام نمی‌رسد | `BOT_TOKEN` یا `CHAT_ID` اشتباه است؛ فاصلهٔ ۳ ساعته؛ یا بدون **force_telegram** اجرا کرده‌اید |
| صفحه همان نسخهٔ قدیمی را نشان می‌دهد | کش مرورگر یا سرویس‌ورکر قدیمی؛ چند بار رفرش کنید |
| لیست مخزن در اسکنر وب «خوانده نشد» | شاخهٔ `data` هنوز ساخته نشده یا گیت‌هاب راو روی اینترنت شما باز نمی‌شود |


## تست با کانفیگ واقعی (آزمایشی، نیاز به Termux یا PC)

مرورگر فقط زمان پاسخ را می‌سنجد؛ `config_test.py` واقعاً از داخل کانفیگ شما با هستهٔ Xray تست می‌کند.

1. در Termux: `pkg install xray` (یا باینری Xray-core را از گیت‌هاب رسمی‌اش بگیرید و در PATH بگذارید).
2. لینک کانفیگ خودتان (`vless://`, `vmess://`, `trojan://`؛ فقط tcp/ws/grpc/httpupgrade با tls یا بدون آن — Reality پشتیبانی نمی‌شود چون CDN ندارد) را آماده کنید.
3. اجرا:
   ```bash
   python config_test.py --config 'vless://...' --ips-file outputs/alive_cloudflare.txt --top 20
   ```
4. خروجی نشان می‌دهد کدام آی‌پی‌ها واقعاً کانفیگ شما را رد می‌کنند، با زمان پاسخ واقعی.
