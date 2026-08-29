import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/ask_model.dart';

class CitationCard extends StatefulWidget {
  final CitationModel citation;
  final int index;
  const CitationCard({super.key, required this.citation, required this.index});

  @override
  State<CitationCard> createState() => _CitationCardState();
}

class _CitationCardState extends State<CitationCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final c    = widget.citation;
    final valid = c.isValid;
    final color = valid ? AppColors.success : AppColors.error;

    return GestureDetector(
      onTap: () => setState(() => _expanded = !_expanded),
      child: Container(
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.25), width: 1),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              child: Row(
                children: [
                  Container(
                    width: 22, height: 22,
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.15),
                      shape: BoxShape.circle,
                    ),
                    child: Center(
                      child: Text('${widget.index}',
                        style: TextStyle(fontFamily: 'Inter', fontSize: 10,
                            fontWeight: FontWeight.w700, color: color)),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Icon(valid ? Icons.check_circle_rounded : Icons.cancel_rounded,
                      size: 14, color: color),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text(
                      c.shortFileName,
                      style: TextStyle(fontFamily: 'Inter', fontSize: 12,
                          fontWeight: FontWeight.w500, color: color),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text('${(c.matchScore * 100).round()}%',
                    style: TextStyle(fontFamily: 'Inter', fontSize: 10,
                        fontWeight: FontWeight.w600, color: color)),
                  const SizedBox(width: 6),
                  Icon(_expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                      size: 16, color: AppColors.textMuted),
                ],
              ),
            ),

            // Expanded quote
            AnimatedSize(
              duration: const Duration(milliseconds: 250),
              curve: Curves.easeInOutCubic,
              child: _expanded
                  ? Padding(
                      padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppColors.background.withValues(alpha: 0.6),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Icon(Icons.format_quote_rounded,
                                    size: 16, color: AppColors.textMuted),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(c.quote,
                                    style: const TextStyle(fontFamily: 'Inter', fontSize: 12,
                                        color: AppColors.textSecondary, height: 1.6,
                                        fontStyle: FontStyle.italic)),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.copy_rounded, size: 14, color: AppColors.textMuted),
                                  padding: EdgeInsets.zero,
                                  constraints: const BoxConstraints(),
                                  onPressed: () {
                                    Clipboard.setData(ClipboardData(text: c.quote));
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      const SnackBar(content: Text('Quote copied'), duration: Duration(seconds: 1)),
                                    );
                                  },
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(c.reason,
                            style: AppTextStyles.caption.copyWith(color: color)),
                        ],
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
          ],
        ),
      ),
    );
  }
}
