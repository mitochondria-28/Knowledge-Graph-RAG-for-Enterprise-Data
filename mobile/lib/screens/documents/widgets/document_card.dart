import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../models/document_model.dart';
import 'package:intl/intl.dart';

class DocumentCard extends StatelessWidget {
  final DocumentModel doc;
  const DocumentCard({super.key, required this.doc});

  @override
  Widget build(BuildContext context) {
    final ext   = doc.extension;
    final color = _extColor(ext);
    final icon  = _extIcon(ext);

    return Container(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.cardBorder, width: 1),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          splashColor: color.withValues(alpha: 0.08),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                // File icon
                Container(
                  width: 46, height: 46,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: Stack(
                    children: [
                      Center(child: Icon(icon, color: color, size: 22)),
                      Positioned(
                        bottom: 4, right: 4,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
                          decoration: BoxDecoration(
                            color: color,
                            borderRadius: BorderRadius.circular(3),
                          ),
                          child: Text(
                            ext.replaceFirst('.', '').toUpperCase(),
                            style: const TextStyle(fontFamily: 'Inter', fontSize: 6,
                                fontWeight: FontWeight.w700, color: Colors.white),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 14),

                // Name + meta
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        doc.filename,
                        style: AppTextStyles.headingMedium,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 5),
                      Row(children: [
                        _Chip(label: doc.typeLabel, color: AppColors.primary),
                        if (doc.displaySize.isNotEmpty) ...[
                          const SizedBox(width: 6),
                          Text(doc.displaySize, style: AppTextStyles.caption),
                        ],
                        if (doc.uploadedAt != null) ...[
                          const SizedBox(width: 6),
                          const Text('·', style: TextStyle(color: AppColors.textMuted, fontSize: 10)),
                          const SizedBox(width: 6),
                          Text(
                            DateFormat('MMM d').format(doc.uploadedAt!),
                            style: AppTextStyles.caption,
                          ),
                        ],
                      ]),
                    ],
                  ),
                ),

                const Icon(Icons.chevron_right_rounded, size: 18, color: AppColors.textMuted),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Color _extColor(String ext) {
    switch (ext) {
      case '.pdf': return AppColors.error;
      case '.md':  return AppColors.secondary;
      default:     return AppColors.accent;
    }
  }

  IconData _extIcon(String ext) {
    switch (ext) {
      case '.pdf': return Icons.picture_as_pdf_rounded;
      case '.md':  return Icons.description_rounded;
      default:     return Icons.article_rounded;
    }
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final Color color;
  const _Chip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: TextStyle(fontFamily: 'Inter', fontSize: 10,
          fontWeight: FontWeight.w600, color: color)),
    );
  }
}
