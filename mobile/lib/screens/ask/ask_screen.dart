import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';
import '../../core/theme/app_theme.dart';
import '../../providers/ask_provider.dart';
import '../../providers/document_provider.dart';
import 'widgets/message_bubble.dart';

class AskScreen extends StatefulWidget {
  const AskScreen({super.key});
  @override
  State<AskScreen> createState() => _AskScreenState();
}

class _AskScreenState extends State<AskScreen> {
  final _controller    = TextEditingController();
  final _scrollCtrl    = ScrollController();
  final _focusNode     = FocusNode();

  @override
  void dispose() {
    _controller.dispose();
    _scrollCtrl.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    _controller.clear();
    await context.read<AskProvider>().ask(text);
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final ask  = context.watch<AskProvider>();
    final docs = context.watch<DocumentProvider>();
    final hasMessages = ask.messages.isNotEmpty;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            // Header
            _Header(onClear: ask.messages.isEmpty ? null : ask.clear)
                .animate().fadeIn(duration: 300.ms),

            // Empty state or messages
            Expanded(
              child: hasMessages
                  ? _MessageList(messages: ask.messages, scrollCtrl: _scrollCtrl)
                  : _EmptyState(docs: docs)
                      .animate().fadeIn(delay: 200.ms),
            ),

            // Input bar
            _InputBar(
              controller: _controller,
              focusNode: _focusNode,
              isThinking: ask.isThinking,
              onSend: _send,
            ).animate().slideY(begin: 1, end: 0, duration: 400.ms, delay: 100.ms, curve: Curves.easeOutCubic),
          ],
        ),
      ),
    );
  }
}

// ── Header ──────────────────────────────────────────────────────────────────
class _Header extends StatelessWidget {
  final VoidCallback? onClear;
  const _Header({this.onClear});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 12),
      child: Row(
        children: [
          Container(
            width: 38, height: 38,
            decoration: BoxDecoration(
              gradient: AppColors.brandGradient,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.hub_rounded, size: 20, color: Colors.white),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Ask KG-RAG', style: AppTextStyles.headingLarge),
                Text('Knowledge graph intelligence', style: TextStyle(
                  fontFamily: 'Inter', fontSize: 12, color: AppColors.textSecondary)),
              ],
            ),
          ),
          if (onClear != null)
            IconButton(
              icon: const Icon(Icons.delete_outline_rounded, size: 20),
              color: AppColors.textMuted,
              onPressed: onClear,
              tooltip: 'Clear conversation',
            ),
        ],
      ),
    );
  }
}

// ── Message list ─────────────────────────────────────────────────────────────
class _MessageList extends StatelessWidget {
  final List messages;
  final ScrollController scrollCtrl;
  const _MessageList({required this.messages, required this.scrollCtrl});

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      controller: scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemCount: messages.length,
      separatorBuilder: (_, __) => const SizedBox(height: 16),
      itemBuilder: (context, i) => MessageBubble(message: messages[i]),
    );
  }
}

// ── Empty state ──────────────────────────────────────────────────────────────
class _EmptyState extends StatefulWidget {
  final dynamic docs;
  const _EmptyState({required this.docs});
  @override
  State<_EmptyState> createState() => _EmptyStateState();
}

class _EmptyStateState extends State<_EmptyState> with SingleTickerProviderStateMixin {
  late AnimationController _anim;

  @override
  void initState() {
    super.initState();
    _anim = AnimationController(vsync: this, duration: const Duration(seconds: 8))..repeat();
  }

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final suggestions = [
      'Who leads the Platform Team?',
      'What technologies does the company use?',
      'Summarize the Q3 strategy document',
      'What projects are currently in progress?',
      'How do the teams collaborate?',
      'What are the main product features?',
    ];

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        children: [
          const SizedBox(height: 20),

          // Animated sphere
          AnimatedBuilder(
            animation: _anim,
            builder: (_, child) {
              final t = _anim.value * 2 * math.pi;
              return Transform.translate(
                offset: Offset(math.sin(t) * 6, math.cos(t * 0.8) * 5),
                child: child,
              );
            },
            child: Container(
              width: 90, height: 90,
              decoration: BoxDecoration(
                gradient: const RadialGradient(colors: [
                  Color(0xFF5B21B6), Color(0xFF2D1B69), Color(0xFF0F0F1A),
                ]),
                shape: BoxShape.circle,
                boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.4), blurRadius: 30)],
              ),
              child: const Icon(Icons.hub_rounded, size: 44, color: Colors.white),
            ),
          ),

          const SizedBox(height: 24),

          const Text(
            'What would you like to know?',
            textAlign: TextAlign.center,
            style: AppTextStyles.headingLarge,
          ),

          const SizedBox(height: 8),

          Text(
            widget.docs.documents.isEmpty
                ? 'Upload a document first, then ask questions about it.'
                : 'Ask anything about your ${widget.docs.documents.length} document${widget.docs.documents.length > 1 ? "s" : ""}.',
            textAlign: TextAlign.center,
            style: AppTextStyles.bodyMedium,
          ),

          const SizedBox(height: 28),

          const Align(
            alignment: Alignment.centerLeft,
            child: Text('Try asking', style: AppTextStyles.label),
          ),
          const SizedBox(height: 12),

          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: suggestions.map((s) => _SuggestionChip(text: s)).toList(),
          ),

          const SizedBox(height: 40),
        ],
      ),
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  final String text;
  const _SuggestionChip({required this.text});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => context.read<AskProvider>().ask(text),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.cardBorder, width: 1),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.lightbulb_outline_rounded, size: 13, color: AppColors.warning),
          const SizedBox(width: 6),
          Flexible(
            child: Text(text, style: const TextStyle(fontFamily: 'Inter', fontSize: 13,
                color: AppColors.textSecondary)),
          ),
        ]),
      ),
    );
  }
}

// ── Input bar ────────────────────────────────────────────────────────────────
class _InputBar extends StatefulWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final bool isThinking;
  final VoidCallback onSend;

  const _InputBar({
    required this.controller,
    required this.focusNode,
    required this.isThinking,
    required this.onSend,
  });

  @override
  State<_InputBar> createState() => _InputBarState();
}

class _InputBarState extends State<_InputBar> {
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(() {
      final has = widget.controller.text.trim().isNotEmpty;
      if (has != _hasText) setState(() => _hasText = has);
    });
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).padding.bottom;
    return Container(
      padding: EdgeInsets.fromLTRB(16, 10, 16, 12 + bottom),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: const Border(top: BorderSide(color: AppColors.cardBorder, width: 1)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Container(
              constraints: const BoxConstraints(maxHeight: 120),
              decoration: BoxDecoration(
                color: AppColors.card,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: AppColors.cardBorder, width: 1),
              ),
              child: TextField(
                controller: widget.controller,
                focusNode: widget.focusNode,
                maxLines: null,
                enabled: !widget.isThinking,
                onSubmitted: (_) => widget.onSend(),
                style: AppTextStyles.bodyLarge,
                decoration: const InputDecoration(
                  hintText: 'Ask a question...',
                  hintStyle: TextStyle(fontFamily: 'Inter', fontSize: 14, color: AppColors.textMuted),
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(horizontal: 18, vertical: 13),
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: 46, height: 46,
            decoration: BoxDecoration(
              gradient: _hasText && !widget.isThinking
                  ? AppColors.brandGradient
                  : const LinearGradient(colors: [Color(0xFF2A2A3E), Color(0xFF1E1E2E)]),
              shape: BoxShape.circle,
              boxShadow: _hasText && !widget.isThinking
                  ? [BoxShadow(color: AppColors.primary.withValues(alpha: 0.4), blurRadius: 12, offset: const Offset(0, 4))]
                  : [],
            ),
            child: IconButton(
              padding: EdgeInsets.zero,
              icon: widget.isThinking
                  ? const SizedBox(width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.send_rounded, size: 20, color: Colors.white),
              onPressed: _hasText && !widget.isThinking ? widget.onSend : null,
            ),
          ),
        ],
      ),
    );
  }
}
