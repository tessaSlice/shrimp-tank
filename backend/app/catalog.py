from __future__ import annotations

from copy import deepcopy


# The people are CRS's published CalHacks sandbox personas. Company financials
# and all business details are fictional teaching data created for this game.
PROFILES = []


def _dollars(amount: int) -> str:
    return "$" + f"{amount:,}"


def _crs_presenter(case: dict) -> dict:
    """Turn a CRS synthetic credit persona into a fictional business pitch."""
    profile = case["profile"]
    # Keep existing session IDs and authored disclosures when a case supplies them.
    return {
        "id": case.get("id", case["sandbox_persona"].lower()),
        "archetype": case["archetype"],
        "company": case["company"],
        "founder": case["founder"],
        "sector": case["sector"],
        "ask_amount": case["ask_amount"],
        "opening_rate": case["opening_rate"],
        "purpose": case["purpose"],
        "opening": case["opening"],
        "public_revenue": case["public_revenue"],
        "sandbox_persona": case["sandbox_persona"],
        "sandbox_expected_score": profile["credit_score"],
        "profile": profile,
        "facts": {
            "character": case["credit_fact"],
            "capacity": case.get(
                "capacity_fact",
                f"We usually have about {_dollars(profile['monthly_free_cash_flow'])} left each month after operating costs, "
                f"with {_dollars(profile['monthly_existing_debt'])} going to existing debt payments.",
            ),
            "capital": case["capital_fact"],
            "collateral": case["collateral_fact"],
            "conditions": case["conditions"],
        },
        "benchmark_context": case["benchmark_context"],
    }


# These are fictional businesses layered over CRS's synthetic credit-report
# cases. Only credit-report facts inform this loan simulation; screening-only
# criminal and eviction records are not used as lending criteria. P14 is a
# deceased-file test and is intentionally not a playable presenter.
PROFILES.extend(_crs_presenter(case) for case in [
    {
        "id": "spindle-loom",
        "archetype": "THE TRAP",
        "company": "Spindle & Loom",
        "founder": "Ricky Dalton",
        "sector": "Circular textiles",
        "ask_amount": 160_000,
        "opening_rate": 9.0,
        "purpose": "Buy reclaimed-fiber inventory and keep two mills running through the holiday season.",
        "opening": "We turn discarded fabric into durable workwear. Two regional retailers are ready to expand our orders, and a $160,000 line would let us buy inventory before the season starts.",
        "public_revenue": 510_000,
        "sandbox_persona": "P05",
        "profile": {
            "credit_score": 540,
            "derogatory_count": 3,
            "thin_file": False,
            "severe_delinquency": True,
            "monthly_free_cash_flow": 7_000,
            "owner_equity": 18_000,
            "collateral": 25_000,
            "market_strength": 48,
            "monthly_existing_debt": 3_100,
        },
        "credit_fact": "My personal credit is 540. I have two collections and a 90-day late payment. I should have brought that up sooner.",
        "capacity_fact": "After payroll and suppliers, we keep about $7,000 a month in free cash. Existing monthly debt payments are around $3,100.",
        "capital_fact": "I have $18,000 of my own cash in the company. Most of our working capital is tied up in inventory.",
        "collateral_fact": "The looms and finished inventory might support about $25,000 of collateral value today.",
        "conditions": "Our two largest buyers account for most of the new orders. The seasonal contract is not guaranteed beyond this year.",
        "benchmark_context": "High personal-credit risk and thin repayment cushion; avoid unless strongly protected.",
    },
    {
        "id": "northstar-cold-chain",
        "archetype": "THE NEGOTIATOR",
        "company": "Northstar Cold Chain",
        "founder": "Priya Venkatesan",
        "sector": "Food logistics",
        "ask_amount": 210_000,
        "opening_rate": 8.0,
        "purpose": "Add two refrigerated vans for a signed regional distribution contract.",
        "opening": "We move temperature-sensitive food for independent grocers. A new regional contract is signed, and I need $210,000 for two refrigerated vans to serve it.",
        "public_revenue": 1_080_000,
        "sandbox_persona": "P08",
        "profile": {
            "credit_score": 690,
            "derogatory_count": 2,
            "thin_file": False,
            "severe_delinquency": False,
            "monthly_free_cash_flow": 24_000,
            "owner_equity": 82_000,
            "collateral": 132_000,
            "market_strength": 72,
            "monthly_existing_debt": 5_500,
        },
        "credit_fact": "My personal credit score is 690. There is a public-record issue I should disclose: an unpaid tax lien and a contractor judgment.",
        "capacity_fact": "Free cash flow averages $24,000 a month after operating costs. Current debt service is about $5,500 a month.",
        "capital_fact": "I have $82,000 of owner equity invested, and I am putting another $30,000 into the van purchase.",
        "collateral_fact": "The refrigerated vans and other equipment have an estimated resale value of $132,000.",
        "conditions": "The contract has a two-year initial term, but our three biggest customers generate 64% of revenue.",
        "benchmark_context": "Good cash generation and collateral offset a public-record concern and customer concentration.",
    },
    {
        "id": "orbit-forge",
        "archetype": "THE UNICORN",
        "company": "Orbit Forge Robotics",
        "founder": "Daniel Whitfield",
        "sector": "Industrial robotics",
        "ask_amount": 220_000,
        "opening_rate": 6.0,
        "purpose": "Expand production capacity for a multi-year factory automation contract.",
        "opening": "We build modular inspection robots for manufacturers. A multi-year factory contract is signed, and $220,000 would let us add a second production cell without slowing delivery.",
        "public_revenue": 2_400_000,
        "sandbox_persona": "P02",
        "profile": {
            "credit_score": 815,
            "derogatory_count": 0,
            "thin_file": False,
            "severe_delinquency": False,
            "monthly_free_cash_flow": 74_000,
            "owner_equity": 190_000,
            "collateral": 184_000,
            "market_strength": 88,
            "monthly_existing_debt": 6_000,
        },
        "credit_fact": "My personal credit score is 815, with a long clean history and no public records.",
        "capacity_fact": "We average $74,000 a month in free cash flow. Existing monthly debt payments are about $6,000.",
        "capital_fact": "The founders have invested $190,000, and we have enough reserves to cover roughly six months of payroll.",
        "collateral_fact": "Our production equipment has an estimated resale value of $184,000, separate from the contract receivable.",
        "conditions": "The factory contract runs for three years and has annual volume commitments. We still rely on one major customer for 38% of sales.",
        "benchmark_context": "Strong credit, cash generation, owner investment, and durable contracted demand.",
    },
    {
        "id": "brightline-pantry",
        "archetype": "THE WILDCARD",
        "company": "Brightline Pantry Labs",
        "founder": "Jasmine Reyes",
        "sector": "Food technology",
        "ask_amount": 145_000,
        "opening_rate": 7.0,
        "purpose": "Fund a pilot production run and secure shelf space with a regional grocer.",
        "opening": "We make shelf-stable meals from surplus produce. A regional grocer wants to run a pilot, and I need $145,000 to fund production and packaging for the first launch.",
        "public_revenue": 330_000,
        "sandbox_persona": "P03",
        "profile": {
            "credit_score": 660,
            "derogatory_count": 0,
            "thin_file": True,
            "severe_delinquency": False,
            "monthly_free_cash_flow": 12_000,
            "owner_equity": 34_000,
            "collateral": 29_000,
            "market_strength": 58,
            "monthly_existing_debt": 2_400,
        },
        "credit_fact": "My personal credit score is 660. I have a short credit history, with only a few accounts reporting.",
        "capacity_fact": "Free cash flow has averaged $12,000 a month, but that includes one-time pilot revenue. Existing debt payments are $2,400.",
        "capital_fact": "I have invested $34,000 of personal funds. The business has about two months of operating expenses in reserve.",
        "collateral_fact": "Packaging equipment and finished goods could support about $29,000 at resale value.",
        "conditions": "We have interest from one grocer, but no minimum-volume commitment. A larger competitor recently entered this category.",
        "benchmark_context": "Thin personal file and uncertain demand call for a smaller, milestone-based facility.",
    },
    {
        "sandbox_persona": "P01", "founder": "Margaret Okafor", "archetype": "THE PHARMACY BUILDER",
        "company": "Willow Creek Pharmacy", "sector": "Community healthcare",
        "ask_amount": 185_000, "opening_rate": 6.5, "public_revenue": 1_260_000,
        "purpose": "Add a second pharmacy counter and extend delivery service to nearby clinics.",
        "opening": "Willow Creek is a neighborhood pharmacy with steady clinic and local-customer demand. I’m seeking $185,000 to add a dispensing counter and expand delivery.",
        "profile": {"credit_score": 790, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 39_000, "owner_equity": 112_000, "collateral": 154_000, "market_strength": 84, "monthly_existing_debt": 7_200},
        "credit_fact": "My CRS sandbox credit file is clean, with a 790 score and no reported public records.",
        "capital_fact": "I have $112,000 of my own equity invested, and the business keeps about four months of operating expenses in reserve.",
        "collateral_fact": "Pharmacy equipment and eligible inventory have an estimated resale value of $154,000.",
        "conditions": "Clinic referrals are stable, but reimbursement timing and pharmacy benefit changes can squeeze margins.",
        "benchmark_context": "Strong credit and cash flow support the request; reimbursement timing remains the main operating risk.",
    },
    {
        "sandbox_persona": "P04", "founder": "Tomas Lindqvist", "archetype": "THE DISTRIBUTOR",
        "company": "Cedar & Coast Provisions", "sector": "Specialty food distribution",
        "ask_amount": 125_000, "opening_rate": 9.5, "public_revenue": 620_000,
        "purpose": "Build cold-storage capacity and fulfill new independent-grocer orders.",
        "opening": "Cedar & Coast supplies specialty pantry goods to independent grocers. I’m asking $125,000 for cold storage and inventory to meet new orders.",
        "profile": {"credit_score": None, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 18_000, "owner_equity": 58_000, "collateral": 76_000, "market_strength": 68, "monthly_existing_debt": 3_000},
        "credit_fact": "I don't really have a credit file yet. The bureaus didn't find one for me, so there's no score to share. That's different from having missed payments.",
        "capital_fact": "I have put $58,000 into the business and kept another $24,000 available for operating needs.",
        "collateral_fact": "Refrigeration equipment and eligible inventory have an estimated resale value of $76,000.",
        "conditions": "Orders are growing, but most come from a handful of independent grocers and are not guaranteed beyond the current season.",
        "benchmark_context": "A missing bureau file calls for verification and alternative repayment evidence; it should not be treated as a zero score.",
    },
    {
        "sandbox_persona": "P06", "founder": "Angela Morrissey", "archetype": "THE MATERIALS RECLAIMER",
        "company": "Maplewood Circular Materials", "sector": "Recycled building supplies",
        "ask_amount": 145_000, "opening_rate": 10.5, "public_revenue": 780_000,
        "purpose": "Purchase sorting equipment and expand reclaimed-lumber inventory.",
        "opening": "We recover usable lumber and fixtures from renovation projects. I need $145,000 for sorting equipment and inventory to serve two new contractors.",
        "profile": {"credit_score": 580, "derogatory_count": 1, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 23_000, "owner_equity": 74_000, "collateral": 98_000, "market_strength": 72, "monthly_existing_debt": 4_300},
        "credit_fact": "My Chapter 7 was discharged in 2024. I’m rebuilding with a secured card; the bankruptcy still appears on the CRS sandbox file.",
        "capital_fact": "I have invested $74,000 in the company, including the first sorting line and a cash reserve.",
        "collateral_fact": "The sorting equipment, delivery truck, and eligible inventory have an estimated resale value of $98,000.",
        "conditions": "Contractor demand is steady, though reclaimed inventory supply varies with the renovation season.",
        "benchmark_context": "Recent recovery and usable collateral matter alongside the discharged bankruptcy; repayment capacity is comparatively strong.",
    },
    {
        "sandbox_persona": "P07", "founder": "Marcus Bellamy", "archetype": "THE FLEET OPERATOR",
        "company": "Peachtree Fleet Services", "sector": "Commercial vehicle maintenance",
        "ask_amount": 195_000, "opening_rate": 13.5, "public_revenue": 1_050_000,
        "purpose": "Replace two service trucks and fund parts inventory for a fleet contract.",
        "opening": "Peachtree services delivery fleets across Atlanta. A new maintenance contract would support two replacement trucks, and I’m seeking $195,000 to put them on the road.",
        "profile": {"credit_score": 560, "derogatory_count": 1, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 31_000, "owner_equity": 63_000, "collateral": 132_000, "market_strength": 70, "monthly_existing_debt": 12_500},
        "credit_fact": "My Chapter 13 repayment plan is active and was filed in 2025. I’m making plan payments, but the filing remains on my credit report.",
        "capital_fact": "I have $63,000 invested in the fleet and repair equipment; current reserves cover about six weeks of expenses.",
        "collateral_fact": "The two service trucks and shop equipment have an estimated resale value of $132,000.",
        "conditions": "The new fleet contract is valuable but concentrated in one customer, and the active repayment plan limits flexibility.",
        "benchmark_context": "An active repayment plan and high existing debt require close review despite strong gross demand and collateral.",
    },
    {
        "sandbox_persona": "P09", "founder": "Derek Holloway", "archetype": "THE FIXTURE MAKER",
        "company": "Front Range Fixture Works", "sector": "Commercial interiors",
        "ask_amount": 155_000, "opening_rate": 7.5, "public_revenue": 930_000,
        "purpose": "Purchase materials and bridge receivables on signed office-fitout projects.",
        "opening": "Front Range builds fixtures for small commercial spaces. We have signed fit-out work waiting on material purchases, and I’m seeking $155,000 to bridge those orders.",
        "profile": {"credit_score": 700, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 27_000, "owner_equity": 82_000, "collateral": 103_000, "market_strength": 73, "monthly_existing_debt": 5_100},
        "credit_fact": "My CRS sandbox credit report shows a 700 score and a clean credit file.",
        "capital_fact": "I have $82,000 invested in the shop and keep about $36,000 in operating reserves.",
        "collateral_fact": "Shop equipment, vehicles, and eligible receivables have an estimated support value of $103,000.",
        "conditions": "The project pipeline is healthy, but payment depends on general contractors approving completed work promptly.",
        "benchmark_context": "A clean, average-strength credit file and signed projects support a measured facility sized to receivables.",
    },
    {
        "sandbox_persona": "P10", "founder": "Lauren Kowalczyk", "archetype": "THE EQUIPMENT SUPPLIER",
        "company": "Woodward Espresso Supply", "sector": "Food-service equipment",
        "ask_amount": 135_000, "opening_rate": 7.0, "public_revenue": 890_000,
        "purpose": "Stock commercial espresso machines ahead of the spring restaurant opening cycle.",
        "opening": "Woodward supplies espresso equipment and service to independent cafés. I’m seeking $135,000 to stock machines before the spring opening season.",
        "profile": {"credit_score": 720, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 25_000, "owner_equity": 68_000, "collateral": 94_000, "market_strength": 76, "monthly_existing_debt": 4_800},
        "credit_fact": "My CRS sandbox credit file is clean and reports a 720 score.",
        "capital_fact": "I have invested $68,000 and retained cash for two months of payroll and rent.",
        "collateral_fact": "The service vans, workshop tools, and eligible equipment inventory have an estimated resale value of $94,000.",
        "conditions": "Recurring service revenue is dependable, but equipment orders are seasonal and inventory can become dated.",
        "benchmark_context": "A clean established file and recurring service revenue support a moderate, inventory-backed facility.",
    },
    {
        "sandbox_persona": "P11", "founder": "Brandon Szabo", "archetype": "THE ROUTE OPERATOR",
        "company": "Highland Route Couriers", "sector": "Local delivery",
        "ask_amount": 105_000, "opening_rate": 11.5, "public_revenue": 540_000,
        "purpose": "Replace aging delivery vans and cover maintenance on a new route.",
        "opening": "Highland Route delivers medical and retail orders across the county. I’m requesting $105,000 to replace two vans and cover maintenance on a newly awarded route.",
        "profile": {"credit_score": 610, "derogatory_count": 1, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 16_000, "owner_equity": 37_000, "collateral": 58_000, "market_strength": 57, "monthly_existing_debt": 5_600},
        "credit_fact": "My credit score is 610. The sandbox public-record case includes a $4,850 judgment.",
        "capital_fact": "I have $37,000 invested in the fleet and keep about $18,000 in working cash.",
        "collateral_fact": "The delivery vans and route equipment have an estimated resale value of $58,000.",
        "conditions": "The new route has a six-month review clause, and vehicle repairs have been taking more cash than planned.",
        "benchmark_context": "Moderate cash flow and a short route commitment call for a smaller, well-secured loan.",
    },
    {
        "sandbox_persona": "P12", "founder": "Victor Anand", "archetype": "THE FREIGHT FOUNDER",
        "company": "Meridian Neighborhood Freight", "sector": "Regional logistics",
        "ask_amount": 160_000, "opening_rate": 10.0, "public_revenue": 860_000,
        "purpose": "Add a loading dock and fund fuel for a new regional distribution route.",
        "opening": "Meridian moves palletized goods between neighborhood suppliers and regional depots. I’m seeking $160,000 to add a dock and start a new route.",
        "profile": {"credit_score": None, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 29_000, "owner_equity": 71_000, "collateral": 88_000, "market_strength": 66, "monthly_existing_debt": 6_500},
        "credit_fact": "The name and Social Security number don't line up in the synthetic file, so the bureaus couldn't match me. I'd want to clear up that identity check before you rely on a score.",
        "capital_fact": "I have $71,000 invested in vehicles and dock equipment, plus a $25,000 operating reserve.",
        "collateral_fact": "The trucks, dock equipment, and eligible receivables have an estimated support value of $88,000.",
        "conditions": "The route is supported by repeat shippers, but the identity mismatch must be resolved before any credit decision.",
        "benchmark_context": "Identity mismatch is a verification hold, not a credit score. Reconcile identity and obtain a valid report before evaluating terms.",
    },
    {
        "sandbox_persona": "P13", "founder": "Kayla Brennan", "archetype": "THE MARKET BUILDER",
        "company": "Kingston Market Studio", "sector": "Specialty retail",
        "ask_amount": 120_000, "opening_rate": 9.0, "public_revenue": 670_000,
        "purpose": "Expand a neighborhood market's prepared-food counter and cold cases.",
        "opening": "Kingston Market pairs local pantry goods with prepared meals. I’m seeking $120,000 for cold cases and a larger kitchen so we can serve nearby offices.",
        "profile": {"credit_score": 640, "derogatory_count": 0, "thin_file": True, "severe_delinquency": False, "monthly_free_cash_flow": 22_000, "owner_equity": 54_000, "collateral": 62_000, "market_strength": 65, "monthly_existing_debt": 4_100},
        "credit_fact": "My credit score is 640 and the file is thin. The sandbox case also flags 9 inquiries in 60 days and identity inconsistencies involving the email, phone, and IP address; those need verification.",
        "capital_fact": "I have invested $54,000 and kept about $28,000 in cash for the expansion.",
        "collateral_fact": "Kitchen equipment, refrigeration, and eligible inventory have an estimated resale value of $62,000.",
        "conditions": "Office lunch demand is promising, but the new kitchen has not yet demonstrated a full year of sales.",
        "benchmark_context": "A thin file limits the evidence available; stage funding against verified sales and installation milestones.",
    },
    {
        "sandbox_persona": "P15", "founder": "Nicole Farragut", "archetype": "THE MARINE OPERATOR",
        "company": "Farragut Marine Repair", "sector": "Marine services",
        "ask_amount": 175_000, "opening_rate": 8.0, "public_revenue": 1_140_000,
        "purpose": "Add a lift and parts inventory before the summer service season.",
        "opening": "Farragut Marine repairs and stores small vessels. I’m requesting $175,000 for a second lift and parts inventory ahead of the summer rush.",
        "profile": {"credit_score": 740, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 36_000, "owner_equity": 104_000, "collateral": 148_000, "market_strength": 78, "monthly_existing_debt": 7_000},
        "credit_fact": "TransUnion has my file frozen, so that report can't give you a score. The synthetic Equifax and Experian results are both 740; I'd want to clear the freeze before relying on the whole picture.",
        "capital_fact": "I have put $104,000 into the yard and equipment, and I’m funding another $26,000 of the lift myself.",
        "collateral_fact": "The lift, service equipment, and eligible parts inventory have an estimated resale value of $148,000.",
        "conditions": "Demand is seasonal and tied to local boating activity, but repeat storage customers provide a stable base.",
        "benchmark_context": "A frozen bureau needs a compliant alternative or consumer action; do not treat the missing bureau result as adverse history.",
    },
    {
        "sandbox_persona": "P16", "founder": "Samuel Oyelaran", "archetype": "THE SOLAR INSTALLER",
        "company": "Brickell Solar Installations", "sector": "Commercial energy",
        "ask_amount": 190_000, "opening_rate": 8.0, "public_revenue": 1_320_000,
        "purpose": "Purchase panels and inverters for three signed commercial installations.",
        "opening": "Brickell installs rooftop solar for small commercial properties. Three projects are signed, and I’m seeking $190,000 to purchase panels and inverters before mobilization.",
        "profile": {"credit_score": 730, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 42_000, "owner_equity": 96_000, "collateral": 118_000, "market_strength": 80, "monthly_existing_debt": 8_500},
        "credit_fact": "My credit file comes back at 730. There's also a fraud alert in the case, so you'd want to verify my identity separately; that alert doesn't show up in this credit report.",
        "capital_fact": "I have invested $96,000 in installation equipment and maintain a $42,000 reserve for project timing.",
        "collateral_fact": "Installation equipment and eligible uninstalled materials have an estimated resale value of $118,000.",
        "conditions": "The signed projects support demand, but milestone payments can arrive after equipment invoices are due.",
        "benchmark_context": "Credit is strong; verify identity separately and structure advances around signed project milestones.",
    },
    {
        "sandbox_persona": "P17", "founder": "Elena Castellanos", "archetype": "THE PACKAGING MAKER",
        "company": "Central Loop Packaging", "sector": "Sustainable packaging",
        "ask_amount": 165_000, "opening_rate": 8.5, "public_revenue": 1_010_000,
        "purpose": "Add a finishing line to fulfill packaging orders from regional food producers.",
        "opening": "Central Loop makes recyclable packaging for regional food producers. We have repeat orders that exceed our current finishing capacity, and I’m seeking $165,000 for a second line.",
        "profile": {"credit_score": 760, "derogatory_count": 1, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 34_000, "owner_equity": 86_000, "collateral": 121_000, "market_strength": 75, "monthly_existing_debt": 6_400},
        "credit_fact": "The reports don't quite agree. TransUnion has me at 760, Equifax couldn't find a file, and Experian shows 700 with one charge-off. I'd want to sort that out before you rely on one number.",
        "capital_fact": "I have $86,000 invested in presses and finishing equipment, with $31,000 held in reserve.",
        "collateral_fact": "The finishing line and eligible receivables have an estimated support value of $121,000.",
        "conditions": "Repeat orders are growing, but a small number of food producers account for most of the volume.",
        "benchmark_context": "Strong cash flow and collateral are encouraging; bureau divergence deserves review rather than blind reliance on a single score.",
    },
    {
        "sandbox_persona": "P18", "founder": "Terrence Abernathy", "archetype": "THE AUTO GLASS OPERATOR",
        "company": "Halsted Auto Glass", "sector": "Vehicle repair",
        "ask_amount": 130_000, "opening_rate": 9.5, "public_revenue": 760_000,
        "purpose": "Replace a curing system and stock glass for commercial fleet accounts.",
        "opening": "Halsted Auto Glass serves drivers and commercial fleets on Chicago's South Side. I’m asking $130,000 to replace a curing system and stock common fleet glass.",
        "profile": {"credit_score": 650, "derogatory_count": 2, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 26_000, "owner_equity": 67_000, "collateral": 87_000, "market_strength": 71, "monthly_existing_debt": 5_200},
        "credit_fact": "I had two charge-offs in 2020 and later paid them. The CRS sandbox profile reports a 650 score, with no newer negative activity in the case summary.",
        "capital_fact": "I have $67,000 invested and keep a $30,000 reserve for parts and payroll.",
        "collateral_fact": "The curing system, service vans, and eligible glass inventory have an estimated resale value of $87,000.",
        "conditions": "Fleet accounts generate repeat work, while insurance reimbursements can take several weeks to clear.",
        "benchmark_context": "A recovery trend and repeat fleet work are positive; confirm recent payment behavior and size the advance to reimbursement timing.",
    },
    {
        "sandbox_persona": "P19", "founder": "Grace Nakamura", "archetype": "THE CAFÉ OWNER",
        "company": "Solano Street Café", "sector": "Hospitality",
        "ask_amount": 225_000, "opening_rate": 7.0, "public_revenue": 1_480_000,
        "purpose": "Open a second café and outfit its kitchen before the lease commencement date.",
        "opening": "Solano Street Café is an owner-operated neighborhood business with strong personal credit behind it. I’m requesting $225,000 to open a second location and outfit the kitchen.",
        "profile": {"credit_score": 770, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 48_000, "owner_equity": 138_000, "collateral": 164_000, "market_strength": 82, "monthly_existing_debt": 9_000},
        "credit_fact": "My CRS sandbox personal credit report is clean and reports a 770 score. The report is personal credit evidence, not a substitute for the café's business statements.",
        "capital_fact": "I have $138,000 committed to the second location and will retain a separate $45,000 opening reserve.",
        "collateral_fact": "Kitchen equipment and eligible business assets have an estimated resale value of $164,000.",
        "conditions": "The first café is profitable, but the second location has a new lease and no established sales history yet.",
        "benchmark_context": "Strong personal credit and owner equity support the request; assess the second location's lease, launch costs, and ramp-up risk separately.",
    },
    {
        "sandbox_persona": "P20", "founder": "Dolores Whitcomb", "archetype": "THE RESTORER",
        "company": "Ocean View Restoration", "sector": "Furniture restoration",
        "ask_amount": 115_000, "opening_rate": 9.0, "public_revenue": 590_000,
        "purpose": "Purchase finishing equipment and fund a move into a larger workshop.",
        "opening": "Ocean View restores furniture for homeowners and boutique hotels. I’m seeking $115,000 for finishing equipment and a larger workshop with room for commercial orders.",
        "profile": {"credit_score": None, "derogatory_count": 0, "thin_file": False, "severe_delinquency": False, "monthly_free_cash_flow": 20_000, "owner_equity": 69_000, "collateral": 82_000, "market_strength": 62, "monthly_existing_debt": 3_200},
        "credit_fact": "I have a long credit history, but every account is closed and the file's been quiet for years. The bureaus couldn't calculate a score, so I don't have a current number for you.",
        "capital_fact": "I have $69,000 invested in tools and the workshop, and I can contribute another $20,000 toward the move.",
        "collateral_fact": "The finishing equipment, workshop tools, and eligible inventory have an estimated resale value of $82,000.",
        "conditions": "Hotel work is repeat business, but the larger lease adds a fixed cost before the new commercial orders are secured.",
        "benchmark_context": "A stale, unscored file calls for current cash-flow evidence and a careful review of the expanded lease commitment.",
    },
])

MAX_OPENING_WORDS = 32
if any(len(pitch["opening"].split()) > MAX_OPENING_WORDS for pitch in PROFILES):
    raise ValueError(f"Every catalog opening pitch must stay within {MAX_OPENING_WORDS} words.")


SHARKS = [
    {
        "id": "kevin", "name": "Kevin O'Leary", "title": "Terms-first investor", "color": "#f2bd6c", "max_grade": 3, "capital": 185_000,
        "ai_profile": {
            "focus": "repayment reliability, cash generation, customer concentration, and lender downside",
            "voice": "blunt, financially specific, and skeptical of unsupported optimism; challenge assumptions without belittling the founder",
            "system_prompt": (
                "Use a fictional Kevin-inspired commercial lens. His public career includes consumer software marketing, acquisitions, "
                "and investment businesses; his public pitch discussions emphasize challenging a founder's business assumptions. "
                "Connect the assigned topic to dependable repayment and recovery if the plan disappoints. Distinguish sales or an "
                "appealing story from money available to repay a loan. Ask for the weakest missing piece of evidence, firmly but "
                "without insults. In a reaction, identify a remaining downside or acknowledge a specific protection; do not reflexively "
                "reject the business. When a founder counters his bid, he usually keeps the original terms and gives ground only "
                "when he is already close. Treat these as game-design priorities, not claims about his private lending policy."
            ),
            "counter_response": {
                "max_gap": 1.5,
                "rate_cut": 0.25,
                "royalty_cut": 0.0,
                "hold": "That counter doesn't change my terms.",
                "budge": "I'll give a quarter point. My rate is now {rate:.2f}%.",
            },
            "game_note": "A fictionalized game profile; not a real-person simulation.",
        },
    },
    {
        "id": "lori", "name": "Lori Greiner", "title": "Product & retail investor", "color": "#86d7c4", "max_grade": 4, "capital": 145_000,
        "ai_profile": {
            "focus": "customer need, repeat demand, product delivery, and cash tied up in fulfilling orders",
            "voice": "encouraging, observant, and practical; acknowledge concrete strengths, then probe an unresolved execution detail",
            "system_prompt": (
                "Use a fictional Lori-inspired product-to-market lens. Her public background covers invention, manufacturing, "
                "patents, and selling consumer products through retail and television. Examine who needs the offering, evidence of "
                "repeat demand, and whether the business can reliably deliver what it sells. Connect the assigned topic to inventory, "
                "fulfillment, or cash timing only where relevant to the supplied business. For a service company, examine service "
                "delivery rather than forcing a retail-product question. Be supportive without treating enthusiasm as evidence. "
                "In a reaction, recognize a concrete strength or practical gap. When a founder counters her bid, she is the most "
                "willing to come down a little, once, and then she holds. Never promise distribution, introductions, or personal help."
            ),
            "counter_response": {
                "max_gap": 4.0,
                "rate_cut": 0.5,
                "royalty_cut": 0.0,
                "hold": "I want this to work, but I'm keeping the offer I made.",
                "budge": "I can come down a little. My rate is now {rate:.2f}%.",
            },
            "game_note": "A fictionalized game profile; not a real-person simulation.",
        },
    },
    {
        "id": "mark", "name": "Mark Cuban", "title": "Scale & operations investor", "color": "#b5a1ff", "max_grade": 3, "capital": 230_000,
        "ai_profile": {
            "focus": "founder execution, repeatable sales, operating bottlenecks, and durable competitive demand",
            "voice": "direct, energetic, and analytical; test how the business works rather than rewarding buzzwords or projections",
            "system_prompt": (
                "Use a fictional Mark-inspired execution lens. His public background includes software systems and building media "
                "businesses; his Shark Tank writing distinguishes pitch claims from later due diligence. Test whether the founder "
                "understands how sales, delivery, costs, and competition fit together. Connect the assigned topic to an operating "
                "bottleneck or how reliable cash generation survives growth. Distinguish demonstrated traction from a forecast, "
                "without assuming a specific technology or growth rate. Be direct and curious rather than dismissive. In a reaction, "
                "identify an execution tradeoff, and acknowledge when the supplied evidence resolves a concern. When a founder "
                "counters his bid, he may trim the rate and royalty once, then he stays put."
            ),
            "counter_response": {
                "max_gap": 3.0,
                "rate_cut": 0.25,
                "royalty_cut": 0.25,
                "hold": "I'm staying with the offer I put down.",
                "budge": "I'll trim the rate to {rate:.2f}%.",
                "budge_royalty": "I'll trim the rate to {rate:.2f}% and the royalty to {royalty:.2f}%.",
            },
            "game_note": "A fictionalized game profile; not a real-person simulation.",
        },
    },
]

SHARK_QUESTIONS = [
    ("conditions", "Who are your largest customers, and how secure are those orders?"),
    ("capacity", "How much free cash is left after payroll, suppliers, and current debt?"),
    ("collateral", "What could you pledge, and what is it worth if the plan misses?"),
]


def get_pitch(pitch_id: str) -> dict:
    for pitch in PROFILES:
        if pitch["id"] == pitch_id:
            return deepcopy(pitch)
    raise KeyError(pitch_id)
