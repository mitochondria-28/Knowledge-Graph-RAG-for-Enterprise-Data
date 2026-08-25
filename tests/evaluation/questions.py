"""
Gold-standard evaluation questions for the TechNova corpus.

QUESTION TAXONOMY:

  simple_entity   — answer is a factual description of one entity
  factual         — answer is a specific fact (date, number, name)
  one_hop         — answer requires one relationship traversal in the graph
  two_hop         — answer requires two relationship traversals
  three_hop       — answer requires three relationship traversals
  multi_entity    — answer spans multiple entities / documents

EXPECTED BEHAVIOR:

  simple_entity + factual  →  vector retrieval wins (semantic similarity)
  one_hop                  →  both perform reasonably (keyword often works too)
  two_hop + three_hop      →  graph retrieval wins (no single chunk has full answer)
  multi_entity             →  both needed; graph gives broader coverage

GROUND TRUTH:

  relevant_sources   — source_file paths whose chunks contain the answer
  expected_entities  — canonical entity names used by the graph retriever
                       to seed its traversal

Source files use the relative paths stored in chunk["source_file"] from
Phase 1 ingestion. These are resolved to chunk_ids at eval time.
"""

from src.evaluation.models import EvalQuestion

QUESTIONS: list[EvalQuestion] = [

    # ── simple_entity ──────────────────────────────────────────────────────────

    EvalQuestion(
        qid="q01",
        question="What is TechNova Corporation and what does it do?",
        question_type="simple_entity",
        relevant_sources=["corpus/companies/technova_overview.md"],
        expected_entities=["TechNova Corporation"],
        notes="Baseline — every retriever should get this right.",
    ),

    EvalQuestion(
        qid="q02",
        question="What is StellarDB and how does it work?",
        question_type="simple_entity",
        relevant_sources=["corpus/technologies/stellar_db_architecture.md"],
        expected_entities=["StellarDB"],
        notes="Answer is almost entirely in stellar_db_architecture.md.",
    ),

    EvalQuestion(
        qid="q03",
        question="What is ApexML and what capabilities does it provide?",
        question_type="simple_entity",
        relevant_sources=["corpus/technologies/apex_ml_platform.md"],
        expected_entities=["ApexML"],
    ),

    EvalQuestion(
        qid="q04",
        question="What is DataBridge and what does it do for TechNova?",
        question_type="simple_entity",
        relevant_sources=["corpus/technologies/data_bridge_etl.md"],
        expected_entities=["DataBridge"],
    ),

    # ── factual ───────────────────────────────────────────────────────────────

    EvalQuestion(
        qid="q05",
        question="When was TechNova Corporation founded and where is it headquartered?",
        question_type="factual",
        relevant_sources=["corpus/companies/technova_overview.md"],
        expected_entities=["TechNova Corporation"],
        notes="Year and city are in the first paragraph of technova_overview.md.",
    ),

    EvalQuestion(
        qid="q06",
        question="When did TechNova acquire Stellar Systems and for how much?",
        question_type="factual",
        relevant_sources=["corpus/companies/stellar_systems_acquisition.md"],
        expected_entities=["TechNova Corporation", "Stellar Systems"],
    ),

    EvalQuestion(
        qid="q07",
        question="When did TechNova acquire Apex Analytics?",
        question_type="factual",
        relevant_sources=["corpus/companies/apex_analytics_acquisition.md"],
        expected_entities=["TechNova Corporation", "Apex Analytics"],
    ),

    EvalQuestion(
        qid="q08",
        question="What data infrastructure does CloudBridge use and why did TechNova partner with them?",
        question_type="factual",
        relevant_sources=["corpus/companies/cloudbridge_partnership.md"],
        expected_entities=["TechNova Corporation"],
        notes="Tests retrieval of a smaller, less prominent document.",
    ),

    # ── one_hop ───────────────────────────────────────────────────────────────

    EvalQuestion(
        qid="q09",
        question="Who leads the Platform Team at TechNova?",
        question_type="one_hop",
        relevant_sources=[
            "corpus/people/engineering_org.md",
            "corpus/technologies/stellar_db_architecture.md",
        ],
        expected_entities=["Platform Team"],
        notes="Platform Team -[LED_BY]-> Aisha Patel. Answer in org chart and StellarDB doc.",
    ),

    EvalQuestion(
        qid="q10",
        question="What technologies does the Platform Team maintain?",
        question_type="one_hop",
        relevant_sources=[
            "corpus/people/engineering_org.md",
            "corpus/technologies/stellar_db_architecture.md",
        ],
        expected_entities=["Platform Team"],
        notes="Platform Team -[MAINTAINS]-> StellarDB, GraphQL Gateway.",
    ),

    EvalQuestion(
        qid="q11",
        question="What teams make up TechNova's Engineering Department?",
        question_type="one_hop",
        relevant_sources=["corpus/people/engineering_org.md"],
        expected_entities=["Engineering Department"],
        notes="Team -[PART_OF]-> Engineering Department. Three teams.",
    ),

    EvalQuestion(
        qid="q12",
        question="Who manages TechNova's engineering teams?",
        question_type="one_hop",
        relevant_sources=["corpus/people/engineering_org.md"],
        expected_entities=["Engineering Department"],
        notes="Marcus Thompson manages all three teams.",
    ),

    # ── two_hop ───────────────────────────────────────────────────────────────

    EvalQuestion(
        qid="q13",
        question="Who leads the team that maintains StellarDB?",
        question_type="two_hop",
        relevant_sources=[
            "corpus/people/engineering_org.md",
            "corpus/technologies/stellar_db_architecture.md",
        ],
        expected_entities=["StellarDB", "Platform Team"],
        notes="StellarDB <-[MAINTAINS]- Platform Team -[LED_BY]-> Aisha Patel. "
              "No single chunk contains the full 2-hop answer.",
    ),

    EvalQuestion(
        qid="q14",
        question="What projects use the technology that Stellar Systems originally developed?",
        question_type="two_hop",
        relevant_sources=[
            "corpus/projects/project_phoenix.md",
            "corpus/projects/project_nexus.md",
            "corpus/companies/stellar_systems_acquisition.md",
        ],
        expected_entities=["Stellar Systems", "StellarDB"],
        notes="Stellar Systems -[DEVELOPED]-> StellarDB <-[USES]- Project Phoenix, Project Nexus.",
    ),

    EvalQuestion(
        qid="q15",
        question="What did TechNova acquire that depends on Apache Kafka?",
        question_type="two_hop",
        relevant_sources=[
            "corpus/companies/stellar_systems_acquisition.md",
            "corpus/companies/apex_analytics_acquisition.md",
            "corpus/technologies/stellar_db_architecture.md",
            "corpus/technologies/apex_ml_platform.md",
        ],
        expected_entities=["Apache Kafka", "TechNova Corporation"],
        notes="Kafka <-[DEPENDS_ON]- StellarDB, ApexML. Both were acquired. 2-hop.",
    ),

    EvalQuestion(
        qid="q16",
        question="Who joined TechNova from the Stellar Systems acquisition and what is their role?",
        question_type="two_hop",
        relevant_sources=[
            "corpus/companies/stellar_systems_acquisition.md",
            "corpus/people/engineering_org.md",
        ],
        expected_entities=["Stellar Systems", "TechNova Corporation"],
        notes="Priya Sharma (formerly Stellar Systems) -[WORKS_FOR]-> TechNova.",
    ),

    # ── three_hop ─────────────────────────────────────────────────────────────

    EvalQuestion(
        qid="q17",
        question="Who leads the team that is responsible for technology developed by a company TechNova acquired?",
        question_type="three_hop",
        relevant_sources=[
            "corpus/people/engineering_org.md",
            "corpus/companies/stellar_systems_acquisition.md",
            "corpus/companies/apex_analytics_acquisition.md",
        ],
        expected_entities=["TechNova Corporation", "StellarDB", "ApexML"],
        notes="3-hop: ACQUIRED -> DEVELOPED -> MAINTAINS -> LED_BY. "
              "This is the canonical hard case — vector retrieval cannot answer it.",
    ),

    EvalQuestion(
        qid="q18",
        question="What projects at TechNova rely on infrastructure from its acquisitions?",
        question_type="three_hop",
        relevant_sources=[
            "corpus/projects/project_phoenix.md",
            "corpus/projects/project_nexus.md",
            "corpus/companies/stellar_systems_acquisition.md",
            "corpus/companies/apex_analytics_acquisition.md",
        ],
        expected_entities=["TechNova Corporation", "Stellar Systems", "Apex Analytics"],
        notes="ACQUIRED -> DEVELOPED -> Tech -> USES -> Project. 3-hop.",
    ),

    # ── multi_entity ──────────────────────────────────────────────────────────

    EvalQuestion(
        qid="q19",
        question="What acquisitions has TechNova made and what technology did each bring?",
        question_type="multi_entity",
        relevant_sources=[
            "corpus/companies/stellar_systems_acquisition.md",
            "corpus/companies/apex_analytics_acquisition.md",
        ],
        expected_entities=["TechNova Corporation", "Stellar Systems", "Apex Analytics"],
        notes="Answer spans two separate acquisition documents.",
    ),

    EvalQuestion(
        qid="q20",
        question="How does Project Nexus integrate StellarDB and ApexML, and who manages it?",
        question_type="multi_entity",
        relevant_sources=[
            "corpus/projects/project_nexus.md",
            "corpus/technologies/stellar_db_architecture.md",
            "corpus/technologies/apex_ml_platform.md",
        ],
        expected_entities=["Project Nexus", "StellarDB", "ApexML", "Sandra Müller"],
        notes="Multi-entity: project details + tech details + person. Both retrievers contribute.",
    ),
]

# Convenience: lookup by qid
QUESTION_BY_ID: dict[str, EvalQuestion] = {q.qid: q for q in QUESTIONS}
