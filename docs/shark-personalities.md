# Shark personality prompts

The investors are fictional teaching characters informed by public business backgrounds. The underwriting questions below are our interpretation of those backgrounds for this loan game, not recovered prompts from the show or claims about the individuals' private lending policies.

## Where the instructions live

- [`backend/app/catalog.py`](../backend/app/catalog.py): each `SHARKS` entry has `ai_profile.system_prompt`, `focus`, and `voice`. The system prompt supplies that character's detailed business lens; the other two fields supply short context summaries.
- [`backend/app/agents.py`](../backend/app/agents.py): `_persona_instructions(shark, next_shark)` combines common dialogue rules with the assigned investor's and reacting investor's system prompts. `_shark_context` separately supplies their names, roles, focus, and communication traits in the request's context JSON.
- `_grok_json_stream` sends the assembled instructions as the actual `system` message and context JSON as the `user` message to xAI Chat Completions, with streaming and a structured response schema. Player questions and transcript strings are treated as untrusted context, not appended to system instructions.

Both player-question exchanges, including the streaming path, and pass/exit exchanges use these instructions. Only the two speakers needed for the exchange are included; this does not introduce separate API requests per shark. Fixed offline templates do not use the new persona prompts.

## Research and the resulting character lenses

Sources were reviewed on October 25, 2026. Source-supported background is separated from our game-design interpretation.

| Character | Public background supporting the profile | Our translation into a loan discussion |
| --- | --- | --- |
| Kevin O'Leary | ABC describes his consumer-software marketing, acquisition, and investment-business background. His account of a Harvard event describes challenging founders' plans and testing customer adoption. [ABC biography](https://abc.com/cast/683912da-1a73-47d9-9e0d-abed4028030a), [pitch discussion](https://kevinoleary.com/news_post/harvard-shark-tanks-kevin-oleary-talks-startups-and-setbacks/) | Ask whether the disclosed business strength creates dependable repayment and what protects against a downside. Challenge the assumption directly while respecting the founder. A good answer can resolve a concern; skepticism is not an automatic rejection. |
| Lori Greiner | ABC and her own biography describe invention, product development, manufacturing, patent work, and retail/television sales. [ABC biography](https://abc.com/cast/6ce5e926-fe88-467a-a276-bd10cfdd3544), [official biography](https://lorigreiner.com/about-lori/) | Examine customer need, repeat demand, and reliable fulfillment. Connect demand to cash needed to deliver orders. Use a practical, encouraging tone and adapt to service businesses instead of assuming every founder sells a retail product. |
| Mark Cuban | ABC's press biography covers software systems, media businesses, and his show participation. His own writing explains why pitch claims require subsequent due diligence. [ABC press biography](https://www.detpress.com/abc/bios/mark-cuban/), [Cuban's explanation of the show](https://blogmaverick.com/2012/02/17/your-quick-and-dirty-guide-to-sharktank/) | Probe execution, repeatable sales, operating bottlenecks, and competitive demand. Ask how the business keeps generating cash as it grows and distinguish demonstrated results from projections. Use a direct, curious tone rather than buzzwords or assumed technology expertise for every case. |

The requested [Wikipedia Shark Tank section](https://en.wikipedia.org/wiki/Mark_Cuban#Shark_Tank) was also reviewed for show context. The linked ABC press biography provides a primary source for Mark despite the absence of a current cast-page link. His game character is based on his historical participation; it does not assert that he remains a current cast member.

The prompt wording is original. Background examples guide the character's reasoning lens; responses should not recite biographies, imitate catchphrases, invent first-person memories, or promise a founder access to the real person's relationships or distribution channels. Promotional success statistics and portfolio totals are not used as evidence that the game predicts loan performance.

## How the prompt controls an exchange

The shared system instructions tell Grok to:

1. Keep the assigned investor on the supplied five-Cs topic and ask one question about one gap.
2. Give the reacting investor a distinct interpretation of the supplied answer, rather than another question or a restatement.
3. Connect the discussion to loan repayment rather than equity valuation.
4. Express uncertain implications conditionally and avoid undisclosed business facts or new numbers.
5. Leave bids, withdrawals, lending approval, founder selection, and risk grades to the Python game engine.

The short-line rules remain: investor questions and reactions are at most 18 words, founder answers at most 30. JSON Schema limits investor strings to 150 characters and founder strings to 260. The existing validators check word length, investor numbers/question ending, and founder numeric consistency with the supplied fact. They do not independently prove personality fidelity or semantic grounding of every sentence.

An example of the intended question lens for each assigned turn, written for this documentation rather than quoted from the show:

| Assigned speaker/topic | Illustrative question |
| --- | --- |
| Kevin / Conditions | If that customer leaves, what keeps loan payments covered? |
| Lori / Capacity | Can you fulfill those orders without using the cash reserved for loan payments? |
| Mark / Collateral | If that equipment is unavailable, how does the business keep delivering? |

## Boundaries and verification

Speaker/topic rotation remains Kevin/Conditions, Lori/Capacity, and Mark/Collateral, with the next investor reacting. These prompts change how a topic is explored; they do not change the round topics, catalog financial values, investor budgets, grade appetite, bid formulas, or scorecard. The backend still makes one structured Grok request per exchange.

Profiles and assembled prompts are application configuration in Python. SpacetimeDB stores the generated conversation but does not retain a dedicated prompt-version history; a resumed session uses the running backend's current instructions for its next generated exchange. There is no prompt lookup table or extra research request during play.

Run the isolated request checks with:

```bash
python -m unittest discover -s backend/tests -v
```

They use mocked xAI streaming responses to check the actual system/user message assembly for all three rounds, player questions and pass/exit exchanges, speaker selection, output limits, and fact-check rejection. They make no paid model calls. Passing these checks verifies wiring and constraints; assessing the naturalness of live Grok dialogue still requires playtesting.
