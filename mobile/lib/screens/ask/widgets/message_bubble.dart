import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/ask_model.dart';
import 'citation_card.dart';

class MessageBubble extends StatefulWidget {
  final ChatMessage message;
  const MessageBubble({super.key, required this.message});

  @override
  State<MessageBubble> createState() => _MessageBubbleState();
}

class _MessageBubbleState extends State<MessageBubble> {
  bool _showCitations = false;

  @override
  Widget build(BuildContext context) {
    final isUser = widget.message.role == MessageRole.user;

    if (widget.message.isLoading) {
      return _TypingIndicator()
          .animate()
          .fadeIn(duration: 300.ms);
    }

    if (isUser) {
      return _UserBubble(text: widget.message.text)
          .animate()
          .fadeIn(duration: 250.ms)
          .slideX(begin: 0.15, end: 0);
    }

    return _AssistantBubble(
      message: widget.message,
      showCitations: _showCitations,
      onToggleCitations: () => setState(() => _showCitations = !_showCitations),
    ).animate().fadeIn(duration: 300.ms).slideX(begin: -0.1, end: 0);
  }
}

class _UserBubble extends StatelessWidget {
  final String text;
  const _UserBubble({required this.text});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
        child: GestureDetector(
          onLongPress: () {
            Clipboard.setData(ClipboardData(text: text));
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Copied'), duration: Duration(seconds: 1)),
            );
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
            decoration: BoxDecoration(
              gradient: AppColors.brandGradient,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(20),
                topRight: Radius.circular(20),
                bottomLeft: Radius.circular(20),
                bottomRight: Radius.circular(4),
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.primary.withValues(alpha: 0.3),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Text(text, style: const TextStyle(fontFamily: 'Inter', fontSize: 14,
                color: Colors.white, height: 1.5)),
          ),
        ),
      ),
    );
  }
}

class _AssistantBubble extends StatelessWidget {
  final ChatMessage message;
  final bool showCitations;
  final VoidCallback onToggleCitations;

  const _AssistantBubble({
    required this.message,
    required this.showCitations,
    required this.onToggleCitations,
  });

  @override
  Widget build(BuildContext context) {
    final resp = message.response;

    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.92),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // AI badge
            Row(children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  gradient: AppColors.brandGradient,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.hub_rounded, size: 12, color: Colors.white),
                    SizedBox(width: 5),
                    Text('KG-RAG', style: TextStyle(fontFamily: 'Inter', fontSize: 10,
                        fontWeight: FontWeight.w700, color: Colors.white)),
                  ],
                ),
              ),
              if (resp != null) ...[
                const SizedBox(width: 8),
                _StrategyBadge(strategy: resp.retrievalStrategy),
              ],
            ]),
            const SizedBox(height: 8),

            // Answer text
            GestureDetector(
              onLongPress: () {
                Clipboard.setData(ClipboardData(text: message.text));
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Copied'), duration: Duration(seconds: 1)),
                );
              },
              child: Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: AppColors.card,
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(4),
                    topRight: Radius.circular(20),
                    bottomLeft: Radius.circular(20),
                    bottomRight: Radius.circular(20),
                  ),
                  border: Border.all(color: AppColors.cardBorder, width: 1),
                ),
                child: MarkdownBody(
                  data: message.text,
                  styleSheet: MarkdownStyleSheet(
                    p: AppTextStyles.bodyLarge,
                    strong: AppTextStyles.bodyLarge.copyWith(fontWeight: FontWeight.w600),
                    code: const TextStyle(fontFamily: 'monospace', fontSize: 13,
                        backgroundColor: Color(0xFF2A2A3E), color: AppColors.secondary),
                    codeblockDecoration: BoxDecoration(
                      color: const Color(0xFF1A1A2E),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    h1: AppTextStyles.headingLarge,
                    h2: AppTextStyles.headingMedium,
                    listBullet: AppTextStyles.bodyLarge,
                  ),
                ),
              ),
            ),

            // Meta + citation toggle
            if (resp != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  _MetaChip(
                    icon: Icons.timer_outlined,
                    label: '${resp.latencyMs.toStringAsFixed(0)}ms',
                  ),
                  const SizedBox(width: 6),
                  _MetaChip(
                    icon: Icons.layers_outlined,
                    label: '${resp.chunkCount} chunks',
                  ),
                  const SizedBox(width: 6),
                  _ConfidencePill(confidence: resp.citationConfidence),
                  const Spacer(),
                  if (resp.citations.isNotEmpty)
                    GestureDetector(
                      onTap: onToggleCitations,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppColors.primary.withValues(alpha: 0.3), width: 1),
                        ),
                        child: Row(mainAxisSize: MainAxisSize.min, children: [
                          Icon(
                            showCitations ? Icons.expand_less_rounded : Icons.format_quote_rounded,
                            size: 14, color: AppColors.primaryLight,
                          ),
                          const SizedBox(width: 4),
                          Text(showCitations ? 'Hide' : '${resp.citations.length} cit.',
                            style: const TextStyle(fontFamily: 'Inter', fontSize: 11,
                                fontWeight: FontWeight.w500, color: AppColors.primaryLight)),
                        ]),
                      ),
                    ),
                ],
              ),

              // Citation list
              if (showCitations && resp.citations.isNotEmpty)
                AnimatedSize(
                  duration: const Duration(milliseconds: 300),
                  curve: Curves.easeInOutCubic,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(height: 10),
                      ...resp.citations.asMap().entries.map((e) =>
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: CitationCard(citation: e.value, index: e.key + 1)
                              .animate().fadeIn(delay: Duration(milliseconds: e.key * 60))
                              .slideY(begin: 0.15, end: 0),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StrategyBadge extends StatelessWidget {
  final String strategy;
  const _StrategyBadge({required this.strategy});

  @override
  Widget build(BuildContext context) {
    Color color;
    IconData icon;
    switch (strategy) {
      case 'graph':  color = AppColors.primary; icon = Icons.hub_rounded; break;
      case 'hybrid': color = AppColors.warning; icon = Icons.merge_type_rounded; break;
      default:       color = AppColors.secondary; icon = Icons.search_rounded;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.3), width: 1),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 11, color: color),
        const SizedBox(width: 4),
        Text(strategy.toUpperCase(),
          style: TextStyle(fontFamily: 'Inter', fontSize: 9, fontWeight: FontWeight.w700, color: color,
              letterSpacing: 0.5)),
      ]),
    );
  }
}

class _MetaChip extends StatelessWidget {
  final IconData icon;
  final String label;
  const _MetaChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(icon, size: 11, color: AppColors.textMuted),
      const SizedBox(width: 3),
      Text(label, style: AppTextStyles.caption),
    ]);
  }
}

class _ConfidencePill extends StatelessWidget {
  final double confidence;
  const _ConfidencePill({required this.confidence});

  @override
  Widget build(BuildContext context) {
    final pct = (confidence * 100).round();
    final color = confidence >= 0.8 ? AppColors.success
        : confidence >= 0.5 ? AppColors.warning
        : AppColors.error;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text('$pct% verified',
        style: TextStyle(fontFamily: 'Inter', fontSize: 10, fontWeight: FontWeight.w600, color: color)),
    );
  }
}

class _TypingIndicator extends StatefulWidget {
  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator> with TickerProviderStateMixin {
  final List<AnimationController> _dots = [];

  @override
  void initState() {
    super.initState();
    for (int i = 0; i < 3; i++) {
      final c = AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 500),
      )..repeat(reverse: true);
      Future.delayed(Duration(milliseconds: i * 150), () {
        if (mounted) c.forward();
      });
      _dots.add(c);
    }
  }

  @override
  void dispose() {
    for (final c in _dots) c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4),
            topRight: Radius.circular(20),
            bottomLeft: Radius.circular(20),
            bottomRight: Radius.circular(20),
          ),
          border: Border.all(color: AppColors.cardBorder, width: 1),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Text('Thinking', style: TextStyle(fontFamily: 'Inter', fontSize: 13, color: AppColors.textSecondary)),
          const SizedBox(width: 8),
          ...List.generate(3, (i) => AnimatedBuilder(
            animation: _dots[i],
            builder: (_, __) => Container(
              margin: const EdgeInsets.symmetric(horizontal: 2),
              width: 6, height: 6,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.primary.withValues(alpha: 0.4 + _dots[i].value * 0.6),
              ),
            ),
          )),
        ]),
      ),
    );
  }
}
