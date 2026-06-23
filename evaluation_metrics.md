Model Used: gemma-4-e4b-it (Open-Weight Model)
Usage Assumptions:

    Total Monthly Queries: 30,000 (100 users x 10 queries/day x 30 days).

    Avg. Input: 1,000 tokens | Avg. Output: 200 tokens.

    Total Volume: 30M Input tokens / 6M Output tokens per month.

Cost Analysis:
    Since gemma-4-e4b-it is an open-model, we evaluated two deployment strategies:
        Self-Hosted (Current Setup): API token cost is 360/month for a dedicated cloud GPU instance to ensure low latency for 100 employees.
        Managed API (Vertex AI/Groq):  Based on current market pricing for small-scale models ($0.10/1M input, $0.20/1M output) the projected cost is only $4.20/month.

Conclusion: For a small internal team of 100 users, using a Managed API is significantly more cost-effective. However, Self-hosting is preferred for maximum data privacy (keeping corporate data inside the internal network).