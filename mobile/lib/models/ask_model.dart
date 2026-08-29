class CitationModel {
  final String chunkId;
  final String sourceFile;
  final String quote;
  final bool isValid;
  final double matchScore;
  final String reason;

  const CitationModel({
    required this.chunkId,
    required this.sourceFile,
    required this.quote,
    required this.isValid,
    required this.matchScore,
    required this.reason,
  });

  factory CitationModel.fromJson(Map<String, dynamic> json) => CitationModel(
        chunkId: json['chunk_id'] as String,
        sourceFile: json['source_file'] as String,
        quote: json['quote'] as String,
        isValid: json['is_valid'] as bool,
        matchScore: (json['match_score'] as num).toDouble(),
        reason: json['reason'] as String,
      );

  String get shortFileName {
    final parts = sourceFile.replaceAll('\\', '/').split('/');
    return parts.last;
  }
}

class AskResponse {
  final String question;
  final String answer;
  final List<CitationModel> citations;
  final double citationConfidence;
  final String retrievalStrategy;
  final String model;
  final double latencyMs;
  final int chunkCount;

  const AskResponse({
    required this.question,
    required this.answer,
    required this.citations,
    required this.citationConfidence,
    required this.retrievalStrategy,
    required this.model,
    required this.latencyMs,
    required this.chunkCount,
  });

  factory AskResponse.fromJson(Map<String, dynamic> json) => AskResponse(
        question: json['question'] as String,
        answer: json['answer'] as String,
        citations: (json['citations'] as List<dynamic>)
            .map((c) => CitationModel.fromJson(c as Map<String, dynamic>))
            .toList(),
        citationConfidence: (json['citation_confidence'] as num).toDouble(),
        retrievalStrategy: json['retrieval_strategy'] as String,
        model: json['model'] as String,
        latencyMs: (json['latency_ms'] as num).toDouble(),
        chunkCount: json['chunk_count'] as int,
      );

  int get validCitations => citations.where((c) => c.isValid).length;
}

// ── Chat messages (local state) ─────────────────────────────────────────────
enum MessageRole { user, assistant }

class ChatMessage {
  final String id;
  final MessageRole role;
  final String text;
  final AskResponse? response;
  final bool isLoading;
  final DateTime createdAt;

  ChatMessage({
    required this.id,
    required this.role,
    required this.text,
    this.response,
    this.isLoading = false,
  }) : createdAt = DateTime.now();
}
