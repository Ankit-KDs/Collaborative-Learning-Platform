# AI-Powered Collaborative Learning and Doubt Resolution Platform

A production-grade, full-stack academic learning and peer collaboration platform built with **Flask**, **SQLite/PostgreSQL**, **Bootstrap 5**, **scikit-learn**, and multi-provider AI integration (**Google Gemini** and **Groq Cloud**).

It matches students who need help with peers who excel in those subjects, supports consent-based private chats and study groups, and resolves doubts through ranked peer answers, teacher verification, duplicate detection, and AI-powered hints, quizzes, and personalized learning paths.

The platform pairs students who find specific subjects challenging with peers who excel in those areas, facilitates structured 1-to-1 and small study group communication, hosts a peer-reviewed doubt resolution forum with faculty verification, and provides Socratic AI study assistance with automated practice quizzes and personalized learning paths.

---

## 🌟 Key Capabilities Across the 8 Stages

| Stage | Module | Key Features |
|:---|:---|:---|
| **Stage 1** | **Architecture & Foundation** | Flask App Factory pattern, Flask-Login authentication, PBKDF2 password hashing, Flask-WTF CSRF protection, base layouts. |
| **Stage 2** | **Profile & Matching** | Academic branch/year management, subject skill levels (Weak, Average, Strong), Greedy Bipartite Matching with dynamic load balancing. |
| **Stage 3** | **Requests & Private Chat** | Buddy request lifecycle, 24-hour decline cooldowns, secure 1-to-1 private chat with incremental long-polling and private media uploads. |
| **Stage 4** | **Study Groups** | Collaborative study groups of 3 to 5 students, admin role delegations, invitation workflow, group chat with system announcements. |
| **Stage 5** | **Doubt Resolution Forum** | Anonymous doubt asking, Merge-Sort answer ranking, peer upvoting (+2 pts), asker acceptance (+10 pts), faculty verification (+15 pts), Knuth-Morris-Pratt search. |
| **Stage 6** | **AI Academic Assistant** | Socratic doubt hints with human escalation, dynamic 5-question multiple choice practice quiz generator with server grading, adaptive learning roadmaps. |
| **Stage 7** | **Safety & Exam Mode** | Aho-Corasick multi-pattern content moderation with evasion normalization (leetspeak, separators), faculty moderation queue, Exam Mode FAQ clustering. |
| **Stage 8** | **Polish & Hardening** | Security headers (CSP, nosniff, X-Frame), sliding-window login rate limiting (5 attempts per 15 min), academic leaderboard, rotating logs, health check. |
| **Stage 9** | **Real-World Readines** | Zero-state default empty DB, strict role-based registration & dashboards, isolated dev seeder (`scripts/dev_seed.py`). |
| **Stage 10** | **Admin Control Center** | Read-focused database viewer, strict privacy & credential redaction, local academic analytics, streaming CSV exports with formula injection mitigation, append-only admin audit log. |

---

## 🏛️ System Architecture

```text
Browser Client (Desktop & Mobile Responsive)
       │
       ▼
Security & Protection Layer (CSP, X-Frame, Nosniff, CSRF, Sliding Rate Limiter)
       │
       ▼
Flask Application Factory (create_app)
  ├── Auth Blueprint (/auth)
  ├── Main & Leaderboard (/dashboard, /leaderboard, /health)
  ├── Matches & Profile (/matches, /profile)
  ├── Requests & Private Chat (/requests, /chats)
  ├── Study Groups (/groups)
  ├── Doubts & Answers (/doubts)
  ├── Quiz & Learning Path (/quiz, /learning-path)
  ├── Moderation Queue (/moderation)
  └── Exam Mode (/exam)
       │
       ▼
Service & Algorithm Layer
  ├── Matching Engine: Greedy Bipartite with Load Balancing (app/services/matching.py)
  ├── Ranking Engine: Divide-and-Conquer Merge Sort (app/services/ranking.py)
  ├── Search Engine: Knuth-Morris-Pratt O(N+M) (app/services/search.py)
  ├── Safety Engine: Aho-Corasick Multi-Pattern Automaton (app/services/moderation.py)
  ├── Similarity Engine: Normalized SHA-256 & TF-IDF Cosine Similarity (app/services/similarity.py)
  └── AI Gateway: Multi-Provider LLM Fallback (Gemini 3.8 Flash & Groq)
       │
       ▼
Data & Storage Layer
  ├── Relational Database (SQLite / PostgreSQL)
  ├── Protected Media Storage (/uploads)
  └── Rotating File Logger (/logs/app.log)
```

---

## ⚙️ Core Data Structures & Algorithms

1. **Greedy Bipartite Matching with Dynamic Load Balancing:**
   - Pairs students having `Weak` subject skills with candidates having `Strong` skills.
   - Filters out overloaded helpers ($load \ge 3$) and breaks ties by same department and year proximity.
   - *Complexity:* $O(N \log N)$
2. **Merge Sort with Custom Quality Comparator:**
   - Sorts doubt answers by: (1) Faculty verification, (2) Accepted answer, (3) Net upvotes, (4) Chronological stability.
   - *Complexity:* $O(N \log N)$ worst-case guaranteed.
3. **Knuth-Morris-Pratt (KMP) Pattern Search:**
   - Precomputes Longest Proper Prefix which is also Suffix (LPS) array for linear text search without backtracking.
   - *Complexity:* $O(N + M)$
4. **Aho-Corasick Multi-Pattern Automaton:**
   - Trie-based state machine with failure transitions for simultaneous multi-word profanity scanning in chat and doubts.
   - Normalized against leetspeak (`@` $\to$ `a`), separators (`f.u.c.k`), and repeated letters.
   - *Complexity:* $O(N + Z)$
5. **Normalized SHA-256 Cryptographic Hashing:**
   - Word-sorted lowercase canonical hashing for $O(1)$ exact duplicate doubt detection.
   - *Complexity:* $O(L)$ hash calculation, $O(1)$ database lookup.
6. **TF-IDF Vectorization & Cosine Similarity:**
   - Computes term-frequency inverse document frequency vectors for duplicate doubt suggestions and Exam Mode FAQ clustering.
   - *Complexity:* $O(D \times W)$

---

## 🚀 Quickstart Installation & Setup

### Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14
- Git

### 1. Clone & Set Up Virtual Environment
```bash
# Clone the repository
git clone https://github.com/your-username/collaborative_learning_platform.git
cd collaborative_learning_platform

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Key configuration settings in `.env`:
```ini
FLASK_APP=run.py
FLASK_CONFIG=development
SECRET_KEY=change-this-to-a-secure-random-32-char-key
DATABASE_URL=sqlite:///instance/learning_platform.db

# Multi-Provider AI (Optional for AI features; offline mode works without keys)
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

# Optional Groq fallback
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b
```

### 4. Database Setup (Starts Empty by Default)
The application starts with a completely empty, clean database ready for user registrations:
```bash
# Verify tables are initialized on startup
python run.py
```

#### Optional: Seed Local Development Data (Dev Only)
To populate sample students, faculty, doubts, and chats for local evaluation, explicitly permit demo seeding:
```bash
# In PowerShell:
$env:ALLOW_DEMO_SEED="true"
python scripts/dev_seed.py

# In Linux / macOS / Bash:
ALLOW_DEMO_SEED=true python scripts/dev_seed.py
```
*(Note: `dev_seed.py` will strictly refuse to execute unless `ALLOW_DEMO_SEED=true` is set, preventing accidental test data pollution in production.)*

### 5. Launch Development Server
```bash
python run.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your web browser.

---

## 👥 Local Development Demo Accounts (When Seeded)

*When populated using `scripts/dev_seed.py`, demo accounts use password: **`demo1234`***

| Email | Role / Academic Standing | Department / Specialization | Purpose in Local Demo |
|:---|:---|:---|:---|
| **`student1@demo.com`** | Student (2nd Year) | Computer Science (B.Tech) | Primary student demo (Aarav Sharma) |
| **`student2@demo.com`** | Student (3rd Year) | Information Tech (B.Tech) | Top peer helper (Priya Patel) |
| **`student3@demo.com`** | Student (4th Year) | Computer Science (B.Tech) | Senior student helper (Rohan Iyer) |
| **`student4@demo.com`** | Student (2nd Year) | Electronics & Comm | Study buddy candidate |
| **`student5@demo.com`** | Student (3rd Year) | Mechanical Eng | Study group collaborator |
| **`teacher1@demo.com`** | Faculty / Associate Prof | Computer Science | Verifies answers & moderates flagged chats |
| **`teacher2@demo.com`** | Faculty / Assistant Prof | Computer Science | Second department faculty reviewer |

---

## 🛡️ Admin Panel & Control Center

The platform includes an administrative control center accessible at `/admin`.

### Creating an Administrator
To prevent privilege escalation attacks, the `admin` role **cannot** be chosen during public registration or edited via profile settings. Admins must be provisioned via the secure CLI utility:

```bash
# Interactive prompt (requires password length >= 10 characters):
python scripts/create_admin.py

# Or via non-interactive arguments:
python scripts/create_admin.py --name "System Admin" --email "admin@collab.edu" --password "StrongAdminPass123"

# Creating additional admins requires explicit override:
python scripts/create_admin.py --force
```

### Key Administrative Capabilities
- **Control Dashboard (`/admin`):** Real-time KPIs (students, faculty, active chats, open vs. solved doubts, pending moderation, AI usage) and 30-day Chart.js registration trends. Safe zero states on fresh deployments.
- **User Management (`/admin/users`):** Directory search, filtering by role/program/year/college/status, sorting, and user detail views (`/admin/users/<id>`). Admins can deactivate/reactivate users (preventing login) and reset moderation strikes. Admins **cannot** deactivate themselves or the last active admin.
- **Database Browser (`/admin/data`):** Read-only tabular explorer across all data models.
  - **Credential Redaction:** Columns matching `password_hash`, tokens, API keys, and secret hashes are automatically stripped from rendering and CSV exports.
  - **Chat Message Privacy:** Message text and image attachments are masked as `[hidden: privacy]` unless `ADMIN_CAN_VIEW_CHAT_CONTENT=true` is explicitly set in `.env`. Every lookup is logged.
  - **Anonymous Doubt Accountability:** Admins can view the real author of anonymous doubts with an accountability tag, and each lookup is permanently recorded in the audit trail.
- **Safety Reports (`/admin/reports`):** 5-tab interface featuring user message reports, auto-flagged messages, blocked submission counts, repeat offenders, and doubt resolution health.
- **Academic Analytics (`/admin/analytics`):** Deterministic local analytics (zero external AI calls) for user demographics, doubt resolution velocity, top peer helpers, request funnels, and quiz metrics.
- **Data Export Center (`/admin/exports`):** Standard and custom streaming CSV downloads. Protects against CSV formula injection by prepending `'` to cells starting with `=`, `+`, `-`, `@`, `\t`, or `\r`.
- **Append-Only Audit Log (`/admin/audit`):** Tracks every administrative action, data export, status change, and IP address. The log has no update or delete routes in the application.

### Optional Admin Environment Configuration
| Variable | Default | Description |
|:---|:---|:---|
| `ADMIN_CAN_VIEW_CHAT_CONTENT` | `false` | When `false`, private & group message bodies are masked as `[hidden: privacy]` in the Data Browser. Set `true` to allow authorized viewing (audited). |
| `ADMIN_IP_ALLOWLIST` | *(empty)* | Optional comma-separated IP list (e.g. `127.0.0.1,192.168.1.100`). When set, access to `/admin` routes from other IPs returns 403 Forbidden. |

---

## 🧪 Testing & Code Quality

The test suite contains 100+ automated unit, integration, security, and end-to-end tests:

```bash
# Run all tests
pytest -v

# Run with test coverage report
pytest --cov=app --cov-report=term-missing
```

---

## 🔒 Security & Hardening Controls

- **CSRF Protection:** Cryptographic token required on all state-modifying POST/PUT/DELETE requests.
- **Session Security:** Cookies configured with `HttpOnly=True`, `SameSite=Lax`, and `Secure=True` in production.
- **Login Rate Limiting:** Sliding-window tracking blocks brute-force attempts (5 failed attempts per 15 minutes per IP/email) with HTTP 429.
- **Security Headers:** Strict headers (`nosniff`, `SAMEORIGIN`, `strict-origin-when-cross-origin`, CSP) applied on all responses.
- **Protected File Storage:** Private doubt and chat attachments stored outside the static directory and served exclusively through authenticated routes.
- **Graceful Degradation:** The platform operates 100% offline if external LLM APIs are unreachable or unconfigured.

---

## 📚 Supplementary Documentation

- [7-8 Minute Presentation Walkthrough Script](docs/DEMO_SCRIPT.md)
- [Algorithmic Foundations & Complexity Analysis](docs/ALGORITHMS.md)
- [30 Master Viva Examination Q&A Defense](docs/VIVA_QA.md)
- [Entity-Relationship (ER) Diagram](docs/ER_DIAGRAM.md)
- [System Architecture & Flow Diagrams](docs/ARCHITECTURE.md)

---

## 📄 License

This capstone project is distributed under the [MIT License](LICENSE).
