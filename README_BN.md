# W8Tracker Bot v3

ব্যবহারকারী Telegram Mini App-এ নিজে সম্মতি দিয়ে ক্যামেরা চালান, ছবি Preview করেন এবং Submit করলে ছবি ও রিপোর্ট **শুধু নিজের Telegram চ্যাটে** পান।

## v2 → v3: কী কী নতুন

**নিরাপত্তা**
- সার্ভারে ছবি পুনরায় এনকোড হয়: EXIF/GPS মুছে যায়, সর্বোচ্চ সাইজে রিসাইজ, decompression-bomb সুরক্ষা
- Rate limit (প্রতি মিনিট ও প্রতি ২৪ ঘণ্টা), CSP ও security headers
- অ্যাপ non-root Docker user-এ চলে, পোর্ট শুধু `127.0.0.1`-এ খোলা
- Metadata whitelist + টাইপ/সাইজ যাচাই (NaN/Infinity বাদ)

**ব্যবহারকারীর নিয়ন্ত্রণ ও স্বচ্ছতা**
- Submit-এর আগে Mini App-এ হুবহু কী যাবে তার JSON দেখা যায়
- "ডিভাইস রিপোর্ট" চালু/বন্ধ (ন্যূনতম মোড)
- `/history` (পেজিনেশন, ছবি আবার দেখা, একটি করে মুছা)
- `/export` (নিজের ডেটা JSON), `/deleteall` (সব ডেটা + চ্যাটের বার্তা মুছা)
- `RETENTION_DAYS` দিনের পর DB রেকর্ড স্বয়ংক্রিয়ভাবে মুছে যায়
- বাংলা/English দুই ভাষা (`/settings`)

**ক্যামেরা অভিজ্ঞতা**
- সামনে/পেছনের ক্যামেরা পরিবর্তন, টর্চ (সমর্থিত হলে), ৩/১০ সেকেন্ড টাইমার
- ক্লায়েন্টে ছবি ছোট করে আপলোড, আপলোড progress bar, haptic feedback
- ২ মিনিট নিষ্ক্রিয় থাকলে বা অ্যাপ ব্যাকগ্রাউন্ডে গেলে ক্যামেরা নিজে বন্ধ হয়

**স্থায়িত্ব ও ডিপ্লয়**
- মডুলার কোড (`app/`), `/healthz`, Docker healthcheck, graceful shutdown
- ঐচ্ছিক Caddy দিয়ে স্বয়ংক্রিয় HTTPS
- ২০টি স্বয়ংক্রিয় টেস্ট (`pytest`)
- v2-এর ডাটাবেস থেকে নিজে নিজেই migrate হয়

## Setup
1. Docker ও একটি ডোমেইন (DNS আপনার সার্ভারে) প্রস্তুত করুন।
2. `.env.example` কপি করে `.env` বানান: `BOT_TOKEN`, `WEBAPP_URL`, `DOMAIN`, `ADMIN_IDS`, শক্তিশালী `POSTGRES_PASSWORD`।
3. Caddy সহ চালান (স্বয়ংক্রিয় HTTPS):
   `docker compose --profile https up -d --build`
   নিজের reverse proxy থাকলে: `docker compose up -d --build` এবং ডোমেইন `127.0.0.1:8000`-এ পাঠান।
4. Telegram-এ বটে `/start` দিন, তারপর Open Camera চাপুন।

## কমান্ড
`/start` `/capture` `/history` `/settings` `/export` `/deleteall` `/privacy` `/help` — Admin: `/stats`

## Optional env
`RETENTION_DAYS=30` · `DAILY_LIMIT=20` · `MINUTE_LIMIT=6` · `MAX_UPLOAD_MB=8` · `MAX_IMAGE_SIDE=2048` · `AUTH_MAX_AGE=3600` · `LOG_LEVEL=INFO`

## টেস্ট চালানো
```
pip install -r requirements-dev.txt
pytest -q
```

## গোপনীয়তা নীতি (ইচ্ছাকৃত ডিজাইন)
IP, GPS/location, contacts, microphone বা hidden fingerprint সংগ্রহ করা হয় না। সম্মতির চেকবক্স, Preview ও Submit ধাপ বাদ দেওয়া যাবে না। Bot Token গোপন রাখুন এবং production-এ নিয়মিত ডাটাবেস backup রাখুন।
