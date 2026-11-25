# Algorithmic Foundations & Complexity Analysis

This document provides comprehensive technical documentation for the **6 core computer science algorithms and data structures** implemented in the **AI-Powered Collaborative Learning and Doubt Resolution Platform**. Each section includes mathematical complexity bounds, trade-off comparisons, and viva examination defense points.

---

## Table of Contents
1. [Greedy Bipartite Matching with Dynamic Load Balancing](#1-greedy-bipartite-matching-with-dynamic-load-balancing)
2. [Merge Sort with Multi-Criteria Custom Comparator](#2-merge-sort-with-multi-criteria-custom-comparator)
3. [Knuth-Morris-Pratt (KMP) String Searching](#3-knuth-morris-pratt-kmp-string-searching)
4. [Aho-Corasick Multi-Pattern String Matching Automaton](#4-aho-corasick-multi-pattern-string-matching-automaton)
5. [Normalized SHA-256 Hashing for Duplicate Detection](#5-normalized-sha-256-hashing-for-duplicate-detection)
6. [TF-IDF Vectorization & Cosine Similarity Clustering](#6-tf-idf-vectorization--cosine-similarity-clustering)

---

## 1. Greedy Bipartite Matching with Dynamic Load Balancing

### Problem Statement
Given a set of students $U$, subjects $S$, and proficiency levels $L = \{\text{Weak}, \text{Average}, \text{Strong}\}$, find optimal study partners such that a student needing help in subject $s \in S$ (where $L(u_{\text{seeker}}, s) = \text{Weak}$) is matched with a helper $u_{\text{helper}}$ where $L(u_{\text{helper}}, s) = \text{Strong}$, without exceeding any helper's maximum cognitive capacity ($\text{MAX\_HELPER\_LOAD} = 3$).

### Implementation Reference
- **Source File:** `app/services/matching.py`
- **Primary Function:** `find_study_buddies(user_id: int, subject: str = None)`

### Mathematical Analysis & Complexity
- **Input:** $N$ registered students, $K$ skills per student, $E$ active connection requests.
- **Filtering Stage:** $O(N)$ scanning eligible candidate students with skill level `'Strong'` for target subject $s$.
- **Sorting / Ranking Stage:**
  - Priority 1: Current active helper load (ascending).
  - Priority 2: Academic proximity (same branch/department: $-1$ penalty score).
  - Priority 3: Academic standing parity ($|\text{year}_{\text{seeker}} - \text{year}_{\text{helper}}|$).
- **Time Complexity:**
  - Filtering: $O(N)$
  - Sorting: $O(M \log M)$, where $M \le N$ is the subset of strong candidates.
  - Overall Time Complexity: $O(N + M \log M) \approx O(N \log N)$ worst-case.
- **Space Complexity:** $O(M)$ auxiliary storage to assemble ranked buddy dictionaries.

### Why Chosen Over Alternatives
- **Alternative Considered:** Hopcroft-Karp Maximum Bipartite Matching ($O(E \sqrt{V})$).
- **Reason for Selection:** Hopcroft-Karp solves an offline, static global matching problem. In a real-time learning platform, buddy requests arrive asynchronously. Students need an immediate, ranked list of recommendations rather than an immutable static assignment. The greedy heuristic ensures zero starvation and dynamically redistributes load as top students accept connections.

### Viva Talking Points
> *"Examiner: Why not use a simple SQL `ORDER BY`?"*  
> **Response:** Pure SQL ordering struggles to compute cross-table dynamic load counts and composite academic proximity metrics cleanly across database backends without complex subqueries. Our Python service computes load in memory from active connections and applies deterministic tie-breakers (department and year parity).

---

## 2. Merge Sort with Multi-Criteria Custom Comparator

### Problem Statement
In a doubt resolution forum, answers must be displayed in order of pedagogical quality. Simple chronological or upvote sorting is vulnerable to vote gaming and ignores authoritative faculty verification.

### Implementation Reference
- **Source File:** `app/services/ranking.py`
- **Primary Function:** `merge_sort(items: list[T], compare_fn: Callable[[T, T], int]) -> list[T]`
- **Domain Comparator:** `compare_answers(a: Answer, b: Answer) -> int`

### Hierarchy Rules
Answers are compared hierarchically across three tiers:
1. **Faculty Verification:** Verified answers strictly precede unverified answers.
2. **Author Accepted:** The solution marked as correct by the doubt author precedes other answers.
3. **Net Upvotes:** Higher score ($\text{upvotes} - \text{downvotes}$) precedes lower score.
4. **Tie-Breaker:** Chronological stability (older answers with the same quality score preserve earlier insertion order).

### Mathematical Analysis & Complexity
- **Divide Step:** Recursively partition list of $N$ answers into halves until sublists of size $1$ are reached ($O(\log N)$ levels).
- **Conquer Step:** Merge two sorted sublists of size $N/2$ in linear time ($O(N)$ comparisons).
- **Time Complexity:**
  - Best Case: $O(N \log N)$
  - Average Case: $O(N \log N)$
  - Worst Case: $O(N \log N)$ (Guaranteed, unlike QuickSort's $O(N^2)$ worst case).
- **Space Complexity:** $O(N)$ auxiliary memory for temporary sub-arrays during merging.

### Why Chosen Over Alternatives
- **QuickSort:** Not inherently stable in standard implementations and suffers from $O(N^2)$ degradation on pre-sorted or equal-key arrays.
- **Python Built-in Timsort:** While Python's `sort()` uses Timsort, implementing Merge Sort demonstrates explicit mastery of divide-and-conquer recurrences ($T(N) = 2T(N/2) + O(N)$) and custom three-way comparators.

---

## 3. Knuth-Morris-Pratt (KMP) String Searching

### Problem Statement
When a student searches for doubt titles or code snippets (e.g., `"NullPointerException in LinkedList"`), naive string searching takes $O(N \times M)$ time when repetitive characters trigger backtracking. KMP guarantees linear search time.

### Implementation Reference
- **Source File:** `app/services/search.py`
- **Primary Functions:** `build_kmp_lps(pattern: str) -> list[int]`, `kmp_search(text: str, pattern: str) -> list[int]`

### LPS (Longest Proper Prefix which is also Suffix) Array
The LPS table records the length of the longest matching proper prefix of `pattern[0...i]` that is also a suffix of `pattern[0...i]`.

$$\text{LPS}[i] = \max \{ k : k < i+1 \land \text{pattern}[0...k-1] = \text{pattern}[i-k+1...i] \}$$

### Complexity Analysis
- **Pattern Preprocessing (LPS Construction):** $O(M)$ time and $O(M)$ space, where $M = |\text{pattern}|$.
- **Text Scanning:** $O(N)$ time, where $N = |\text{text}|$. Each character of the text is evaluated at most twice (via pointer increment and LPS lookup).
- **Total Time Complexity:** $O(N + M)$ strictly linear.
- **Space Complexity:** $O(M)$ to store the LPS array.

### Comparison Table

| Algorithm | Preprocessing Time | Search Time (Worst Case) | Space Complexity | Backtracking in Text? |
|:---|:---:|:---:|:---:|:---:|
| **Naive Search** | $0$ | $O(N \times M)$ | $O(1)$ | Yes |
| **Rabin-Karp** | $O(M)$ | $O(N \times M)$ | $O(1)$ | No (Hash collisions) |
| **Boyer-Moore** | $O(M + |\Sigma|)$ | $O(N \times M)$ | $O(|\Sigma|)$ | Yes |
| **KMP (Our Choice)** | **$O(M)$** | **$O(N + M)$** | **$O(M)$** | **Never** |

---

## 4. Aho-Corasick Multi-Pattern String Matching Automaton

### Problem Statement
A collaborative educational platform requires real-time content moderation for chat messages and doubt submissions. Checking $K$ profane words independently with single-string matching requires $O(K \times N)$ time. Furthermore, students attempt evasions (leetspeak, repeated letters, spacing).

### Implementation Reference
- **Source File:** `app/services/moderation.py`
- **Primary Class:** `AhoCorasick`
- **Normalization Function:** `normalize_for_moderation(text: str) -> str`

### Data Structure & Architecture
The Aho-Corasick automaton constructs a finite-state machine combining:
1. **Trie Structure:** Shared prefix tree representing the bad-words dictionary.
2. **Failure Links (Fallback Transitions):** Constructed via Breadth-First Search (BFS) using the longest proper suffix of the current state that exists in the trie (analogous to KMP's LPS applied across trees).
3. **Output Dictionaries:** Set of matched patterns emitted at each state.

```
       (root)
      /      \
    [b]      [f]
    /          \
  [a]          [u]
  /              \
[d]*             [c]
                   \
                   [k]*
```

### Preprocessing Normalization Pipeline
Before passing text to the automaton, text undergoes four normalization stages:
1. **Unicode Lowercasing:** `Casefold()` standardizes characters.
2. **Leetspeak Translation:** Maps `@` $\to$ `a`, `$` $\to$ `s`, `1` $\to$ `i`, `0` $\to$ `o`, `!` $\to$ `i`, `3` $\to$ `e`.
3. **Zero-Width & Punctuation Stripping:** Removes non-alphanumeric separators (`f.u.c.k` $\to$ `fuck`).
4. **Run-Length Compression:** Collapses 3+ repeated characters (`fuuuuuck` $\to$ `fuuck`).
5. **Scunthorpe Whitelist Protection:** Ensures innocent words containing sub-patterns (e.g., *"class"*, *"document"*, *"associate"*) are excluded from false-positive flagging.

### Mathematical Complexity
- **Trie & Automaton Construction:** $O(\sum_{i=1}^{K} M_i)$, where $M_i$ is length of word $i$.
- **Text Traversal:** $O(N + Z)$ time, where $N$ is text length and $Z$ is total number of occurrences found.
- **Space Complexity:** $O(\sum M_i \times |\Sigma|)$ for state transition tables.

---

## 5. Normalized SHA-256 Hashing for Duplicate Detection

### Problem Statement
Students frequently re-post identical doubts across semesters with minor whitespace, capitalization, or punctuation differences. Exact duplicate detection must execute in $O(1)$ database lookup time without executing expensive vector models on identical submissions.

### Implementation Reference
- **Source File:** `app/services/similarity.py`
- **Primary Function:** `compute_content_hash(subject: str, title: str, body: str) -> str`

### Normalization Pipeline
$$\text{Input} \xrightarrow{\text{Lowercase}} \xrightarrow{\text{Strip Punctuation}} \xrightarrow{\text{Tokenize & Sort Words}} \xrightarrow{\text{SHA-256}} \text{64-character Hex Hash}$$

```python
normalized_text = f"{subject.lower()}|{' '.join(sorted(clean_tokens))}"
content_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
```

### Complexity
- **Hashing Time:** $O(L)$, where $L$ is combined byte length of title and body.
- **Database Lookup Time:** $O(1)$ average lookup via B-Tree index on `Doubt.content_hash`.
- **Space Complexity:** 64 bytes fixed storage per doubt.

---

## 6. TF-IDF Vectorization & Cosine Similarity Clustering

### Problem Statement
When a doubt is not an exact textual duplicate, it may still express the same underlying conceptual query (e.g., *"How do I invert a binary tree in Python?"* vs. *"Inverting a BST recursively"*). Furthermore, **Exam Mode** requires automatically clustering related questions into synthesized FAQ review guides.

### Implementation Reference
- **Source File:** `app/services/similarity.py`
- **Functions:** `find_similar_doubts()`, `cluster_doubts_for_exam_mode()`

### Mathematical Model
1. **Term Frequency (TF):**
   $$\text{TF}(t, d) = \frac{f_{t, d}}{\sum_{t' \in d} f_{t', d}}$$
2. **Inverse Document Frequency (IDF):**
   $$\text{IDF}(t, D) = \ln \left( \frac{1 + |D|}{1 + |\{d \in D : t \in d\}|} \right) + 1$$
3. **Cosine Similarity Metric:**
   $$\text{Similarity}(\mathbf{u}, \mathbf{v}) = \cos(\theta) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\|_2 \|\mathbf{v}\|_2} = \frac{\sum_{i=1}^{V} u_i v_i}{\sqrt{\sum_{i=1}^V u_i^2} \sqrt{\sum_{i=1}^V v_i^2}}$$

### Complexity Analysis
- **Corpus Fitting & Vectorization:** $O(D \times W)$, where $D$ is count of subject doubts and $W$ is average word count.
- **Pairwise Dot-Product:** $O(D \times V)$ where $V$ is vocabulary size.
- **Space Complexity:** $O(D \times V)$ sparse matrix representation.
