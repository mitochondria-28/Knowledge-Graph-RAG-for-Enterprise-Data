"""
Evaluation harness — runs retrievers and computes metrics per question.

FLOW:

  1. Receive a list of EvalQuestions and a source_file → chunk_ids mapping
  2. For each question, resolve relevant chunk IDs from relevant_sources
  3. Run each registered retriever
  4. Compute P@k, R@k, F1@k, MRR for each (question, retriever) pair
  5. Aggregate per-retriever EvalReports with macro averages and type breakdown

SOURCE FILE → CHUNK ID RESOLUTION:

  Questions define relevance by source_file (portable across re-ingestion).
  The harness converts these to chunk_ids at runtime using the chunk_index
  built from all_chunks.json. If a source_file isn't in the index (e.g.
  a typo), a warning is logged and that source contributes 0 relevant chunks.
"""

import logging
from collections import defaultdict

from src.evaluation.metrics import (
    f1_at_k,
    macro_average,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from src.evaluation.models import (
    EvalQuestion,
    EvalReport,
    QuestionScore,
    RetrievalResult,
)
from src.evaluation.retriever_base import BaseRetriever

logger = logging.getLogger(__name__)


def build_source_index(chunks: list[dict]) -> dict[str, list[str]]:
    """
    Build source_file → [chunk_ids] mapping from all_chunks.json data.
    Used to resolve question.relevant_sources into actual chunk IDs.
    """
    index: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        index[chunk["source_file"]].append(chunk["chunk_id"])
    return dict(index)


def _resolve_relevant(
    question: EvalQuestion,
    source_index: dict[str, list[str]],
) -> set[str]:
    """Return the set of chunk_ids relevant for this question."""
    relevant: set[str] = set()
    for src in question.relevant_sources:
        if src in source_index:
            relevant.update(source_index[src])
        else:
            logger.warning("q%s: source %r not found in chunk index", question.qid, src)
    return relevant


class EvaluationHarness:
    """
    Runs multiple retrievers over a question set and produces EvalReports.

    Args:
        retrievers:    List of BaseRetriever instances (keyword, vector, graph, …)
        source_index:  {source_file: [chunk_id, …]} from build_source_index()
        k:             Number of results to retrieve per question. Default 5.
    """

    def __init__(
        self,
        retrievers: list[BaseRetriever],
        source_index: dict[str, list[str]],
        k: int = 5,
    ) -> None:
        self._retrievers = retrievers
        self._source_index = source_index
        self._k = k

    def run(self, questions: list[EvalQuestion]) -> list[EvalReport]:
        """
        Run all retrievers over all questions and return one EvalReport per retriever.
        """
        # retriever_name → list[QuestionScore]
        scores_by_retriever: dict[str, list[QuestionScore]] = defaultdict(list)

        for question in questions:
            relevant = _resolve_relevant(question, self._source_index)
            if not relevant:
                logger.warning(
                    "q%s (%s): no relevant chunks found — question will score 0",
                    question.qid, question.question[:40],
                )

            for retriever in self._retrievers:
                result: RetrievalResult = retriever.retrieve(question, self._k)

                score = QuestionScore(
                    qid=question.qid,
                    question=question.question,
                    question_type=question.question_type,
                    retriever=retriever.name,
                    precision_at_k=precision_at_k(result.retrieved_chunk_ids, relevant, self._k),
                    recall_at_k=recall_at_k(result.retrieved_chunk_ids, relevant, self._k),
                    f1_at_k=f1_at_k(result.retrieved_chunk_ids, relevant, self._k),
                    mrr=reciprocal_rank(result.retrieved_chunk_ids, relevant),
                    retrieved_count=len(result.retrieved_chunk_ids),
                    relevant_count=len(relevant),
                    k=self._k,
                )
                scores_by_retriever[retriever.name].append(score)
                logger.debug(
                    "  %-12s q%-3s  P@%d=%.2f  R@%d=%.2f  F1=%.2f  MRR=%.2f",
                    retriever.name, question.qid,
                    self._k, score.precision_at_k,
                    self._k, score.recall_at_k,
                    score.f1_at_k, score.mrr,
                )

        return [
            self._build_report(name, scores)
            for name, scores in scores_by_retriever.items()
        ]

    def _build_report(self, retriever_name: str, scores: list[QuestionScore]) -> EvalReport:
        # Macro averages
        macro_p  = macro_average([s.precision_at_k for s in scores])
        macro_r  = macro_average([s.recall_at_k for s in scores])
        macro_f1 = macro_average([s.f1_at_k for s in scores])
        macro_mrr = macro_average([s.mrr for s in scores])

        # Per-type breakdown
        by_type: dict[str, list[QuestionScore]] = defaultdict(list)
        for s in scores:
            by_type[s.question_type].append(s)

        type_summary: dict[str, dict[str, float]] = {}
        for qtype, type_scores in by_type.items():
            type_summary[qtype] = {
                "precision": macro_average([s.precision_at_k for s in type_scores]),
                "recall":    macro_average([s.recall_at_k    for s in type_scores]),
                "f1":        macro_average([s.f1_at_k        for s in type_scores]),
                "mrr":       macro_average([s.mrr            for s in type_scores]),
                "count":     len(type_scores),
            }

        return EvalReport(
            retriever=retriever_name,
            k=self._k,
            scores=scores,
            macro_precision=macro_p,
            macro_recall=macro_r,
            macro_f1=macro_f1,
            macro_mrr=macro_mrr,
            by_type=type_summary,
        )
