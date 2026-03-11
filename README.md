# 🤖 UzBiznesBot v4.1

Telegram orqali biznes bot yaratuvchi platform.

## 🚀 Railway ga deploy qilish

### 1. GitHub ga yuklash

```bash
git init
git add .
git commit -m "UzBiznesBot v4.1"
git branch -M main
git remote add origin https://github.com/SIZNING_USERNAME/uzbiznest-bot.git
git push -u origin main
```

### 2. Railway da yangi loyiha

1. [railway.app](https://railway.app) ga kiring
2. **New Project** → **Deploy from GitHub repo**
3. Reponi tanlang
4. **Settings → Variables** ga o'ting

### 3. Environment Variables qo'shish

Railway da **Variables** bo'limiga quyidagilarni qo'shing:

| Key | Value |
|-----|-------|
| `MAIN_TOKEN` | BotFather dan olgan token |
| `SUPER_ADMIN_ID` | Sizning Telegram ID |

### 4. Deploy

Variables qo'shilgandan keyin Railway avtomatik deploy qiladi.  
**Deployments** bo'limida loglarni kuzating.

---

## 💻 Local ishga tushirish

```bash
# 1. Kutubxonalar o'rnatish
pip install -r requirements.txt

# 2. .env fayl yaratish
cp .env.example .env
# .env faylga tokenlarni kiriting

# 3. Ishga tushirish
python main.py
```

---

## ⚠️ Muhim eslatma

Railway bepul tарифda oyiga **500 soat** beradi.  
Bot 24/7 ishlashi uchun **Hobby plan** ($5/oy) kerak.

---

## 📁 Fayl tuzilmasi

```
uzbiznest/
├── main.py          # Asosiy bot kodi
├── requirements.txt # Kutubxonalar
├── Procfile         # Railway ishga tushirish
├── .gitignore       # Git ignore
├── .env.example     # Token namunasi
└── README.md        # Shu fayl
```
