# Project Demonstration Script (7-8 Minute Walkthrough)

**Project Name:** AI-Powered Collaborative Learning and Doubt Resolution Platform  
**Target Audience:** Final Year Viva Examiners, Faculty Reviewers, and Project Evaluators  
**Estimated Duration:** 7 to 8 Minutes  

---

## 0. Pre-Flight Checklist (Run Before Calling Examiners)

The platform is designed to run in production with an initially empty database. For demonstration and viva presentation purposes, you can either register live accounts or prepare demo accounts using the isolated dev seeder:

### Option A (Recommended for Complete Demo Flow):
Prepare demo data in your local development environment:
```bash
# 1. Enable demo seeding flag
# In PowerShell:
$env:ALLOW_DEMO_SEED="true"
# Or in Bash:
# export ALLOW_DEMO_SEED=true

# 2. Run the isolated dev seeder
.\venv\Scripts\python.exe scripts/dev_seed.py

# 3. Start the server
.\venv\Scripts\python.exe run.py
```

### Option B (Clean Start Flow):
Demonstrate live role-specific registration:
1. Register a **Student** with college details, roll number, program (B.Tech/CSE), year, semester.
2. Register a **Faculty** member with official ID, department, and the secure invite code (`TEACHER_INVITE_CODE=faculty-secret-code-2026`).

Open two browser windows:
- **Window A (Student):** `http://127.0.0.1:5000` (Login: `student1@demo.com` / `demo1234` or newly registered student)
- **Window B (Faculty):** `http://127.0.0.1:5000` (Login: `teacher1@demo.com` / `demo1234` or newly registered teacher)

---

## Demo Timeline & Script

### Minute 0:00 – 1:00: Introduction & The Problem Statement
- **Screen:** Logged-out Landing Page (`/`).
- **Talking Points:**
  - *"Good morning/afternoon, esteemed evaluators. Today I am presenting our capstone project: the **AI-Powered Collaborative Learning and Doubt Resolution Platform**."*
  - *"In traditional university environments, students often hesitate to ask basic doubts in large classrooms for fear of judgment, and top students get overwhelmed with repetitive peer queries. Existing forums like StackOverflow are generic and lack syllabus context."*
  - *"Our platform solves this through an end-to-end engineered system integrating **bipartite peer matching**, **merge-sorted doubt resolution with teacher verification**, **multi-pattern Aho-Corasick safety moderation**, and **Socratic Gemini/Groq AI assistance**."*
- **Action:** Point out the clean landing page hero, feature pillars, and click **"View Leaderboard"** to demonstrate that public reputation standings are visible without leaking student doubt anonymity.

---

### Minute 1:00 – 1:45: Student Sign-In & Dynamic Dashboard
- **Screen:** Window A (`/auth/login` -> `/dashboard`).
- **Action:** Log in as `student1@demo.com` (Aarav Sharma).
- **Talking Points:**
  - *"Notice our authentication system includes strict session cookie protection (`HttpOnly`, `SameSite=Lax`), CSRF tokens on every form, and sliding-window rate limiting (5 failed attempts per 15 minutes)."*
  - *"Upon login, the student arrives at their **Personalized Academic Dashboard**. It dynamically reflects pending buddy requests, study group invites, active doubts asked, quizzes taken, and subject reputation scores with honor tier badges (Helper, Expert, Guru)."*

---

### Minute 1:45 – 2:45: Smart Peer Matching (Greedy Algorithm)
- **Screen:** Window A -> Navigate to **"Matches"** (`/matches`).
- **Action:**
  - Show the list of recommended study buddies for subjects Aarav is **Weak** in (e.g., Data Structures, Mathematics).
  - Point out that every matched helper is **Strong** in that subject.
  - Explain load balancing:
    - *"Notice how helpers with fewer active commitments are ranked higher. This uses a **Greedy Bipartite Matching algorithm** with a strict helper capacity limit (`MAX_HELPER_LOAD = 3`) to avoid burnout."*
  - Click **"Send Request"** to invite a classmate. Show flash message and instant status update.

---

### Minute 2:45 – 3:45: Private Chat & Study Groups (Stage 3 & 4)
- **Screen:** Window A -> Navigate to **"Chats"** and **"Groups"** (`/chat` & `/groups`).
- **Action:**
  - Open an existing private chat room with a matched buddy.
  - Show real-time message polling, image attachment preview, and timestamp rendering.
  - Switch to **"Groups"** (`/groups`):
    - *"To encourage collaborative projects, students can form small study groups of 3 to 5 members."*
    - Show an active group room (e.g., "Algorithms Mastermind Group").
    - Highlight system messages ("User X joined the group") and member role management (Admin vs. Member).

---

### Minute 3:45 – 5:00: Doubt Forum, KMP Search & Reputation (Stage 5)
- **Screen:** Window A -> Navigate to **"Doubts"** (`/doubts`).
- **Action:**
  - Type a query in the search bar: e.g., `"Binary Tree"` or `"B+ Tree"`.
  - Explain:
    - *"Search uses the **Knuth-Morris-Pratt (KMP) algorithm**, which preprocesses pattern prefixes into an LPS array for $O(N + M)$ worst-case search time without backtracking."*
  - Open a solved doubt:
    - Show the **Merge Sort Ranking** in action: answers are sorted with Teacher-Verified answers on top, followed by Accepted solutions, followed by Net Upvotes.
    - Upvote an answer -> observe live reputation score change (+2 pts).
    - Point out the **Anonymous Doubt** feature:
      - *"Students can check 'Post Anonymously'. The asker's identity is cryptographically hidden across all public views and API responses, eliminating doubt-asking anxiety."*

---

### Minute 5:00 – 6:00: Socratic AI Hint, Practice Quiz & Learning Path (Stage 6)
- **Screen:** Window A -> Doubt Details / Quiz (`/doubts/<id>` and `/quiz`).
- **Action:**
  - On an open doubt without answers, click **"Request AI Hint"**:
    - Show how the AI provides a **Socratic guiding hint** (does NOT spoil the answer or write full code).
    - If the student clicks "This didn't help", demonstrate how the doubt is automatically tagged with `needs_human` and escalated to classmates.
  - Navigate to **"Quiz"** (`/quiz`):
    - Show an AI-generated 5-question multiple choice test.
    - Submit answers -> show immediate client-safe server-side grading, explanations, and score history.
  - Navigate to **"Learning Path"** (`/learning-path`):
    - Show the radar chart and generated roadmap dynamically targeting subjects where the student has marked **Weak**.

---

### Minute 6:00 – 7:00: Content Moderation & Teacher Review Queue (Stage 7)
- **Screen:** Switch to Window B (Logged in as `teacher1@demo.com` - Faculty).
- **Action:**
  - Open **"Moderation"** queue (`/moderation`).
  - Demonstrate:
    - Show flagged chat messages detected by the **Aho-Corasick Multi-Pattern Automaton**.
    - Explain evasion defenses: leetspeak translation (`b!tch` -> `bitch`), repeated characters (`fuuuuck`), and zero-width separators (`f.u.c.k`).
    - Explain Scunthorpe problem prevention: innocent words like *"class"* or *"document"* are never flagged.
    - Teacher clicks **"Confirm Violation"** -> user's strike count increments; or **"Dismiss"** -> message restored.
  - Switch to Doubts forum -> teacher clicks **"Verify Answer"** on an outstanding student solution -> awards **+15 reputation points** to the author.

---

### Minute 7:00 – 8:00: Exam Mode Revision & Conclusion
- **Screen:** Window A -> Navigate to **"Exam Mode"** (`/exam`).
- **Action:**
  - Select subject: **"Data Structures"**.
  - Show how doubts are automatically grouped into **FAQ clusters** using **TF-IDF Vectorization and Cosine Similarity**, with the highest-ranked accepted or verified solution displayed as the canonical quick-revision answer.
- **Closing Statement:**
  - *"To summarize, our platform is a complete, secure, production-tested Flask application powered by 6 rigorous data structures and algorithms, verified across 99 automated tests with comprehensive test coverage. Thank you, and we welcome your questions!"*

---

## Emergency Viva Fallback Plan

| Scenario | Quick Fix |
|:---|:---|
| **No Internet / Gemini API Key Expired** | Switch `.env` to `AI_PROVIDER=groq` or demonstrate graceful fallback error banner. Non-AI features (matching, doubts, chats, moderation, leaderboard) are 100% offline-ready. |
| **Accidentally deleted records** | Re-run `.\venv\Scripts\python.exe seed.py` (idempotent, regenerates all demo records in 2 seconds). |
| **Examiner asks to see tests** | Run `.\venv\Scripts\pytest -v` in terminal to display all tests passing green. |
