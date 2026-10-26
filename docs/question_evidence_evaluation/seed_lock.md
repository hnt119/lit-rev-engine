# Seed identities, development and held-out lock

Status: **no seeds selected or locked**. Use `templates/seeds.csv`; no provided examples are gold.

1. Establish explicit identifiers from an authoritative bibliographic record. A DOI without an established PMID stays unresolved for current PubMed membership checks; never guess identity.
2. Before checking a query, record why each seed is in the test scope, database coverage/date/filters, source evidence, selection role and independent reviewer approval. Eligibility for this evaluation is not formal systematic-review inclusion.
3. Mark construction seeds as development for the entire experiment. Keep separately selected held-out identities/answers away from term tuning. Record a cryptographic digest of each locked list, timestamp and responsible person outside participant materials.
4. Lock the candidate query/version before the held-out check. The current diagnostic action permits at most three approved seeds and two provider calls; preserve it. Larger independent checks need a separately approved budget and transport, not repeated hidden UI calls.
5. Record query membership and capped-preview recovery in separate columns, with exact query receipt/date. Provider errors, missing PMID, unverified coverage and unavailable checks remain unresolved/NOT_RUN and do not enter a misleading recall denominator.

Report the count of established, in-scope, independently held-out seeds matched divided by the number actually checked with established coverage, plus unresolved/excluded counts and reasons. Name the metric **known-paper recovery**, not literature recall. A development result, small diagnostic sample or manually curated public example cannot establish independent retrieval accuracy.
