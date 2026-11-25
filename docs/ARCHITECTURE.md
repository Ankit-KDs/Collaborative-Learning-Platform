# System Architecture & Flow Diagrams

This document illustrates the tiered architectural design and request data flows of the **AI-Powered Collaborative Learning and Doubt Resolution Platform**.

---

## 1. High-Level Tiered System Architecture

```mermaid
flowchart TD
    subgraph Client_Tier [Client Presentation Tier]
        Browser["Modern Web Browser (Desktop / Mobile)"]
        UI_Components["Bootstrap 5 + Jinja2 + Polling Engine"]
    end

    subgraph App_Tier [Flask Application & Security Tier]
        AppFactory["Flask Application Factory (create_app)"]
        SecHeaders["Security Headers Hook (CSP, nosniff, X-Frame)"]
        RateLimiter["Sliding-Window Rate Limiter (5 per 15 min)"]
        AuthModule["Flask-Login & Flask-WTF CSRF"]
        Blueprints["12 Modular Blueprints (Auth, Doubts, Chat, etc.)"]
    end

    subgraph Service_Tier [Algorithmic & Service Business Layer]
        MatchService["Greedy Buddy Matching Engine"]
        RankService["Merge Sort Custom Quality Comparator"]
        SearchService["KMP String Search Engine"]
        ModerationService["Aho-Corasick Moderation Automaton"]
        SimilarityService["SHA-256 & TF-IDF Cosine Similarity"]
        AIService["Multi-Provider LLM Gateway (Gemini / Groq)"]
    end

    subgraph Storage_Tier [Persistence & Storage Tier]
        DB[(Relational DB: SQLite / PostgreSQL)]
        Uploads["Secure File Storage (/uploads)"]
        Logs["Rotating File Logger (/logs/app.log)"]
    end

    subgraph AI_Cloud [External AI Cloud Services]
        GeminiAPI["Google Gemini API (gemini-3.8-flash)"]
        GroqAPI["Groq Cloud API (openai/gpt-oss-20b)"]
    end

    Browser <--> UI_Components
    UI_Components <--> SecHeaders
    SecHeaders --> RateLimiter
    RateLimiter --> AuthModule
    AuthModule --> Blueprints
    Blueprints --> Service_Tier
    Service_Tier <--> DB
    Service_Tier <--> Uploads
    Service_Tier --> Logs
    AIService <--> GeminiAPI
    AIService <--> GroqAPI
```

---

## 2. Sequence Diagram: Algorithmic Buddy Matching

```mermaid
sequenceDiagram
    autonumber
    actor Student as Student (Seeker)
    participant Route as Matches Blueprint (/matches)
    participant Service as Matching Service (matching.py)
    participant DB as SQLite Database
    actor Helper as Strong Classmate (Helper)

    Student->>Route: GET /matches (Views Weak Subjects)
    Route->>Service: find_study_buddies(student_id)
    Service->>DB: Query students with 'Strong' in Seeker's 'Weak' subjects
    DB-->>Service: Return Candidate Helper List
    Service->>DB: Query active request count for each candidate
    DB-->>Service: Active Connection Counts
    Note over Service: Filter out overloaded helpers (load >= 3)<br/>Sort by: (1) Lower Load, (2) Same Branch, (3) Year Parity
    Service-->>Route: Return Ranked Helpers
    Route-->>Student: Display Ranked Study Buddies
    Student->>Route: POST /requests/send (Selects Helper)
    Route->>DB: Create BuddyRequest(status='pending')
    DB-->>Helper: Helper sees pending invitation on Dashboard
```

---

## 3. Sequence Diagram: Doubt Posting & Duplicate Prevention

```mermaid
sequenceDiagram
    autonumber
    actor Student as Student
    participant Route as Doubts Blueprint (/doubts/new)
    participant Moderation as Moderation Service (Aho-Corasick)
    participant Similarity as Similarity Service (SHA-256 + TF-IDF)
    participant DB as SQLite Database

    Student->>Route: POST /doubts/new (Title, Subject, Body)
    Route->>Moderation: filter_text(Title + Body)
    alt Profanity / Evasion Detected
        Moderation-->>Route: Profanity detected
        Route-->>Student: Reject with HTTP 400 Bad Request
    else Content Clean
        Route->>Similarity: compute_content_hash(Subject, Title, Body)
        Similarity->>DB: Check if content_hash already exists
        alt Exact Duplicate Detected
            Similarity-->>Route: Duplicate Found (Existing Doubt ID)
            Route-->>Student: Redirect with notice: "Identical doubt already exists"
        else Unique Doubt
            Route->>DB: Insert Doubt record
            Route-->>Student: Redirect to Doubt Details page
        end
    end
```

---

## 4. Sequence Diagram: Aho-Corasick Message Moderation

```mermaid
sequenceDiagram
    autonumber
    actor User as Chat Participant
    participant ChatRoute as Chat Blueprint (/chats/<id>/send)
    participant ModService as Aho-Corasick Automaton
    participant DB as SQLite Database
    actor Teacher as Faculty Reviewer

    User->>ChatRoute: POST /chats/<id>/send (Message Text)
    ChatRoute->>ModService: check_text(Message Text)
    Note over ModService: 1. Unicode casefolding<br/>2. Leetspeak mapping (@ -> a, 1 -> i)<br/>3. Punctuation stripping (f.u.c.k -> fuck)<br/>4. Multi-pattern Trie search with failure links
    alt Message Violates Policy
        ModService-->>ChatRoute: Flagged (pattern matched)
        ChatRoute->>DB: Save Message with review_status='pending',<br/>original_text preserved for faculty,<br/>masked text shown in room
        DB-->>Teacher: Increments Pending Moderation count
    else Message Clean
        ChatRoute->>DB: Save Message with review_status='none'
        ChatRoute-->>User: Message delivered in real time
    end
```
