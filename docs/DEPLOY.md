# BOLL BILL: deployment steps

Total time: lagbhag 45 minute (pehli baar). Cost: shuru me sab free ho sakta hai, sirf AI (Grok) use ke hisaab se paisa lagta hai.

**Kaam ka order (isi order me karein):**
1. Supabase (database + login)  →  2. Grok API key  →  3. AI service ko Render par  →  4. HTML ko Netlify par  →  5. Dono ko ek dusre ka address batana  →  6. Test

Aapko chahiye: email se bane free accounts: **Supabase**, **xAI**, **GitHub**, **Render**, **Netlify**.

> Sab kuch ek saath live karne ki zarurat nahi. Agar sirf login + cloud save chahiye, to step 1, 4, 5 kaafi hain. AI baad me (step 2, 3) jod sakte hain.

---

## Step 1: Supabase (database + login)

1. supabase.com par login karke **New project** banayein.
   - Name: `bollbill`
   - Database password: koi strong password banakar kisi safe jagah save kar lein.
   - Region: **South Asia (Mumbai)**, taaki data India me rahe aur speed achhi mile.
2. Project ban jaye (1-2 minute), phir left menu se **SQL Editor → New query** kholein.
3. `supabase/schema.sql` file poori kholkar copy karein, query box me paste karein, **Run** dabayein.
   - Neeche "Success" aana chahiye. Error aaye to poora error message mujhe bhej dein.
4. **Table Editor** me check karein ki ye tables dikh rahe hain: `shops`, `items`, `bills`, `agent_runs`, `agent_actions`.
5. **Authentication** section me:
   - Email sign-in chalu hona chahiye (by default chalu hota hai).
   - Abhi testing ke liye **Confirm email** band kar dein. Isse signup ke turant baad login ho jata hai. Live karne se pehle ise dobara chalu karna behtar hai.
6. **Project Settings → API Keys** kholkar ye 2 cheezein kisi notepad me copy kar lein:
   - **Project URL**, jaise `https://abcdxyz.supabase.co`
   - **Publishable key**, jo `sb_publishable_...` se shuru hoti hai.
   - Agar aapke project me "Create new API keys" ka button dikhe, to pehle use dabakar publishable key bana lein. Purane project me legacy `anon` key bhi isi jagah chalti hai.

⚠️ **Secret key (`sb_secret_...`) ya `service_role` key kabhi bhi HTML me ya kisi dost ko na bhejein.** Is project me inki zarurat hi nahi hai.

---

## Step 2: Grok API key

1. console.xai.com par account banayein, aur Billing me thode credits daalein.
2. **API Keys → Create key**. `sk-ant-...` wali key copy karke notepad me rakh lein.
3. Settings me **monthly spend limit** zarur lagayein, taaki galti se zyada kharch na ho.

Ye key sirf Step 3 me Render par jayegi. HTML me kabhi nahi.

---

## Step 3: AI service ko Render par chadhana

**3a. Code GitHub par daalein**
1. github.com par **New repository** banayein, naam `bollbill`, **Private** rakhein.
2. Apne computer par `bollbill` folder me terminal kholkar:
   ```
   git init
   git add .
   git commit -m "BOLL BILL first version"
   git branch -M main
   git remote add origin https://github.com/AAPKA-NAAM/bollbill.git
   git push -u origin main
   ```
3. GitHub par repo me check karein ki `.env` file upload **nahi** hui (`.gitignore` use rok deta hai).

**3b. Render par service banayein**
1. render.com par GitHub se login karein → **New → Web Service** → apna `bollbill` repo chunein.
2. Ye fields bharein:
   | Field | Value |
   |---|---|
   | Language | **Docker** |
   | Root Directory | `backend` |
   | Instance Type | Free (testing ke liye) |
   | Health Check Path | `/health` |
3. **Environment Variables** me ye add karein:
   | Name | Value |
   |---|---|
   | `SUPABASE_URL` | Step 1 ka Project URL |
   | `SUPABASE_ANON_KEY` | Step 1 ki **Publishable key** (naam anon hai, par key publishable wali hi daalein) |
   | `GROK_API_KEY` | Step 2 ki `sk-ant-...` key |
   | `ALLOWED_ORIGINS` | abhi `http://localhost:5500` likh dein, Step 5 me badlenge |
   | `MODEL_FAST` | `grok-haiku-5-5` |
   | `MODEL_SMART` | `grok-sonnet-5-5` |
   | `DAILY_AI_LIMIT` | `200` (har user ke liye din me AI calls ki limit) |
4. **Create Web Service** dabayein. Pehli build me kuch minute lagte hain.
5. Ban jane par upar ek address dikhega, jaise `https://bollbill-ai.onrender.com`. Use copy kar lein.
6. Browser me `https://bollbill-ai.onrender.com/health` kholein. `{"ok":true}` dikhna chahiye.

> Free plan par service 15 minute koi use na ho to so jati hai. Uske baad pehla AI sawaal 30-60 second le sakta hai. Asli dukaan ke liye Render ka paid plan lein, jo hamesha chalu rehta hai. Plans aur daam Render ke pricing page par dekh lein, ye badalte rehte hain.

---

## Step 4: HTML (website) ko Netlify par chadhana

1. `frontend/index.html` ko apne editor me kholein (Notepad bhi chalega). Upar `BB_CONFIG` dhoondhein aur teeno values bharein:
   ```js
   window.BB_CONFIG = {
     SUPABASE_URL: "https://abcdxyz.supabase.co",
     SUPABASE_ANON_KEY: "sb_publishable_....",
     AGENT_API_URL: "https://bollbill-ai.onrender.com"
   };
   ```
   Address ke aakhir me `/` na lagayein. Save karein.
2. Ek naya folder banayein, jaise `bollbill-site`, aur usme sirf `index.html` rakhein. Naam bilkul `index.html` hona chahiye.
3. app.netlify.com/drop kholein aur **folder** (file nahi) khinch kar chhod dein.
4. Netlify ek address dega, jaise `https://random-name.netlify.app`. Use copy kar lein.
5. Ye site bina account ke banai gayi to Netlify use thodi der baad hata deta hai. Isliye turant **sign up / claim** karke apne account me save kar lein.
6. HTML badalne par naya folder usi site ke **Deploys** page par dobara drag kar dein.

---

## Step 5: Dono ko ek dusre ka address batana

1. **Supabase → Authentication → URL Configuration:**
   - **Site URL** me Netlify ka address daalein (`https://random-name.netlify.app`).
   - **Redirect URLs** me bhi wahi address add karein.
   - Isse email confirm wale link sahi jagah khulte hain.
2. **Render → apni service → Environment:**
   - `ALLOWED_ORIGINS` ko Netlify ke address par badal dein. Bilkul waisa hi likhein: `https://` ke saath, aakhir me `/` ke bina.
   - Save karne par Render apne aap dobara chalta hai.

---

## Step 6: Test karein (is order me)

1. Netlify ka address kholein. Landing page dikhna chahiye.
2. **Start BOLL BILL** → email aur password se Sign up → business name, UPI, GST (skip bhi kar sakte hain) → app khul jana chahiye.
3. Supabase **Table Editor** me dekhein: `shops` me aapki dukaan ki ek row, aur `items` me price list honi chahiye.
4. App me ek bill banayein. Thodi der me `bills` table me ek row aani chahiye.
5. Phone me wahi address kholkar usi email se login karein. Wahi items aur bills dikhne chahiye.
6. **Assistant** tab dikhna chahiye. Poochiye: *"Aaj ki bikri kitni hui?"*
7. Ek **Udhaar** bill banayein (customer ka naam daalkar). Phir Assistant se bolein: *"Rahul ka udhaar paid kar do."* Wo "Haan / Nahi" ka box dikhayega. **Haan** dabane ke baad bill paid ho jana chahiye.
8. Bill tab me 🤖 **AI se bill banao** ke box me likhein: `2 kilo aata aur 1 litre tel`. Items bill me jud jane chahiye.
9. Supabase me `agent_runs` table dekhein: har AI sawaal ki ek row dikhni chahiye.

Sab pass ho gaya to live hain. 🎉

---

## Live karne se pehle (security checklist)

- [ ] Supabase me **Confirm email** dobara chalu kiya. Email bhejne ki default limit bahut kam hoti hai, isliye asli users ke liye Authentication me apna email provider (SMTP) jodein.
- [ ] xAI par monthly spend limit laga hai.
- [ ] HTML me sirf URL aur **publishable** key hai, koi `secret` ya `service_role` key nahi.
- [ ] GitHub repo **Private** hai aur usme `.env` nahi hai.
- [ ] Render par `ALLOWED_ORIGINS` me sirf aapki site ka address hai.
- [ ] Supabase se data ka backup/export lene ka tarika dekh liya hai. Free plan ki shartein (pause hona, backup) Supabase ke pricing page par check karein.
- [ ] Aakhri kaam ke taur par, jo bhi key kabhi chat ya screenshot me dikh gayi ho, use dashboard se naya bana lein.

---

## Agar kuch na chale

| Problem | Kya karein |
|---|---|
| Browser console me **CORS** error | Render me `ALLOWED_ORIGINS` Netlify ke address se bilkul match nahi karta. `https://`, spelling, aur aakhir ka `/` check karein. |
| Assistant tab / AI button dikhta hi nahi | `BB_CONFIG` me teeno values bharni zaruri hain, aur HTML dobara Netlify par drag karna padta hai. |
| Signup ka email nahi aata | Testing me **Confirm email** band rakhein. Live ke liye custom SMTP jodein. |
| "Login expire ho gaya" | Dobara login karein. Phir bhi aaye to Render ki `SUPABASE_URL` aur key sahi hain ya nahi dekhein. |
| AI bolta hai "Pehle apni dukaan ki details save karein" | Onboarding poori nahi hui. Logout karke dobara login karein aur business details bharein. |
| "AI se jawab nahi mil paya" | Render → **Logs** dekhein. Aksar xAI key galat hai, credits khatam hain, ya model ka naam galat hai. |
| Pehla AI jawab bahut der se aaya | Render ka free plan so gaya tha. Dobara try karein, ya paid plan lein. |
| SQL me `permission denied for function` | `schema.sql` poori dobara Run karein (ye dobara chalane se kuch nahi bigadta). |
| Render deploy me "Missing environment variables" | Step 3b ke teeno zaruri variables (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `GROK_API_KEY`) add karein. |
| "Aaj ki AI limit poori ho gayi" | `DAILY_AI_LIMIT` badhayein ya kal tak ruken. |

Phir bhi atke to browser console (F12 → Console) ka laal error aur Render ke Logs ka aakhri hissa bhej dein. Usse jaldi pata chal jata hai.

---

## Baad me update karna

- **AI service ka code badla:** `git push` karein. Render aam taur par apne aap naya version chalu kar deta hai (agar Auto-Deploy chalu hai).
- **HTML badla:** naya folder usi Netlify site par dobara drag karein.
- **Database badla:** naya SQL Supabase SQL Editor me chalayein. Purane data ka backup pehle le lein.

---

## (Optional) Pehle apne computer par chalakar dekhna

```
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env   (phir .env me values bharein)
uvicorn app.main:app --reload --port 8000
```
`.env` me `ALLOWED_ORIGINS=http://localhost:5500` rakhein. Doosre terminal me `frontend` folder me `python -m http.server 5500` chalakar `http://localhost:5500` kholein. HTML ko seedha double-click karke (`file://`) na kholein, warna browser AI service ko block kar deta hai. `BB_CONFIG` me `AGENT_API_URL: "http://localhost:8000"` rakhein.
