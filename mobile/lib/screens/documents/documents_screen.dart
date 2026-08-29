import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:percent_indicator/percent_indicator.dart';
import 'package:provider/provider.dart';
import '../../config/app_config.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/shimmer_box.dart';
import '../../providers/document_provider.dart';
import 'widgets/document_card.dart';

class DocumentsScreen extends StatefulWidget {
  const DocumentsScreen({super.key});
  @override
  State<DocumentsScreen> createState() => _DocumentsScreenState();
}

class _DocumentsScreenState extends State<DocumentsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final p = context.read<DocumentProvider>();
      if (p.status == DocumentStatus.idle) p.fetchDocuments();
    });
  }

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'md', 'txt'],
      allowMultiple: false,
    );
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    if (file.path == null) return;
    if ((file.size) > AppConfig.maxUploadBytes) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('File too large. Max 10 MB.'), backgroundColor: AppColors.error),
        );
      }
      return;
    }

    // Show type picker
    final type = await _showTypePicker();
    if (type == null || !mounted) return;

    await context.read<DocumentProvider>().uploadDocument(
      filePath: file.path!,
      fileName: file.name,
      docType: type,
    );

    if (mounted) {
      final prov = context.read<DocumentProvider>();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(prov.uploadResult ?? prov.error ?? 'Upload complete'),
          backgroundColor: prov.error != null ? AppColors.error : AppColors.success,
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  Future<String?> _showTypePicker() {
    return showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(width: 36, height: 4,
                  decoration: BoxDecoration(color: AppColors.cardBorder,
                      borderRadius: BorderRadius.circular(2))),
              ),
              const SizedBox(height: 20),
              const Text('Document Type', style: AppTextStyles.headingLarge),
              const SizedBox(height: 6),
              const Text('How should KG-RAG categorize this document?',
                style: TextStyle(fontFamily: 'Inter', fontSize: 13, color: AppColors.textSecondary)),
              const SizedBox(height: 20),
              ...AppConfig.docTypes.map((t) => _TypeTile(
                type: t,
                onTap: () => Navigator.pop(context, t),
              )),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final docs = context.watch<DocumentProvider>();

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
              child: Row(
                children: [
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Documents', style: AppTextStyles.displayMedium),
                        SizedBox(height: 2),
                        Text('Your private knowledge base',
                          style: TextStyle(fontFamily: 'Inter', fontSize: 13, color: AppColors.textSecondary)),
                      ],
                    ),
                  ),
                  // Upload FAB inline
                  GestureDetector(
                    onTap: docs.isUploading ? null : _pickAndUpload,
                    child: Container(
                      height: 44,
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      decoration: BoxDecoration(
                        gradient: AppColors.brandGradient,
                        borderRadius: BorderRadius.circular(22),
                        boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.35), blurRadius: 14, offset: const Offset(0, 4))],
                      ),
                      child: const Row(mainAxisSize: MainAxisSize.min, children: [
                        Icon(Icons.upload_rounded, size: 18, color: Colors.white),
                        SizedBox(width: 6),
                        Text('Upload', style: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600,
                            fontSize: 13, color: Colors.white)),
                      ]),
                    ),
                  ),
                ],
              ),
            ).animate().fadeIn(duration: 300.ms),

            // Upload progress bar
            if (docs.isUploading)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
                child: _UploadProgress(progress: docs.uploadProgress),
              ).animate().fadeIn(),

            const SizedBox(height: 16),

            // Content
            Expanded(
              child: docs.isLoading
                  ? const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 24),
                      child: ShimmerList(count: 5),
                    )
                  : docs.documents.isEmpty
                      ? _EmptyState(onUpload: _pickAndUpload)
                          .animate().fadeIn(delay: 200.ms)
                      : RefreshIndicator(
                          color: AppColors.primary,
                          backgroundColor: AppColors.card,
                          onRefresh: docs.fetchDocuments,
                          child: ListView.separated(
                            padding: const EdgeInsets.fromLTRB(24, 0, 24, 120),
                            itemCount: docs.documents.length,
                            separatorBuilder: (_, __) => const SizedBox(height: 10),
                            itemBuilder: (context, i) {
                              return DocumentCard(doc: docs.documents[i])
                                  .animate()
                                  .fadeIn(delay: Duration(milliseconds: i * 50))
                                  .slideX(begin: 0.1, end: 0);
                            },
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

class _UploadProgress extends StatelessWidget {
  final double progress;
  const _UploadProgress({required this.progress});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.3), width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const SizedBox(width: 8, height: 8,
              child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.primary)),
            const SizedBox(width: 10),
            const Text('Uploading document...', style: TextStyle(fontFamily: 'Inter',
                fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.textPrimary)),
            const Spacer(),
            Text('${(progress * 100).round()}%',
              style: const TextStyle(fontFamily: 'Inter', fontSize: 12, color: AppColors.primary,
                  fontWeight: FontWeight.w600)),
          ]),
          const SizedBox(height: 10),
          LinearPercentIndicator(
            lineHeight: 4,
            percent: progress,
            backgroundColor: AppColors.cardBorder,
            linearGradient: AppColors.brandGradient,
            barRadius: const Radius.circular(2),
            padding: EdgeInsets.zero,
            animation: false,
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onUpload;
  const _EmptyState({required this.onUpload});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80, height: 80,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF0E4F6A), Color(0xFF1A0A2E)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                shape: BoxShape.circle,
                boxShadow: [BoxShadow(color: AppColors.secondary.withValues(alpha: 0.3), blurRadius: 24)],
              ),
              child: const Icon(Icons.cloud_upload_outlined, size: 38, color: AppColors.secondary),
            ),
            const SizedBox(height: 24),
            const Text('No documents yet', style: AppTextStyles.headingLarge, textAlign: TextAlign.center),
            const SizedBox(height: 10),
            const Text(
              'Upload PDF, Markdown, or text files.\nEach document goes into your private knowledge base.',
              textAlign: TextAlign.center,
              style: TextStyle(fontFamily: 'Inter', fontSize: 14, color: AppColors.textSecondary, height: 1.6),
            ),
            const SizedBox(height: 28),
            GestureDetector(
              onTap: onUpload,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
                decoration: BoxDecoration(
                  gradient: AppColors.brandGradient,
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.4), blurRadius: 20, offset: const Offset(0, 6))],
                ),
                child: const Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.upload_file_rounded, size: 18, color: Colors.white),
                  SizedBox(width: 10),
                  Text('Upload Your First Document',
                    style: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600,
                        fontSize: 14, color: Colors.white)),
                ]),
              ),
            ),
            const SizedBox(height: 16),
            const Text('Supports .pdf  ·  .md  ·  .txt  (max 10 MB)',
              style: TextStyle(fontFamily: 'Inter', fontSize: 12, color: AppColors.textMuted)),
          ],
        ),
      ),
    );
  }
}

class _TypeTile extends StatelessWidget {
  final String type;
  final VoidCallback onTap;
  const _TypeTile({required this.type, required this.onTap});

  static const _icons = {
    'general':    Icons.article_rounded,
    'company':    Icons.business_rounded,
    'project':    Icons.rocket_launch_rounded,
    'technology': Icons.code_rounded,
    'people':     Icons.people_rounded,
  };

  static const _colors = {
    'general':    AppColors.accent,
    'company':    AppColors.secondary,
    'project':    AppColors.primary,
    'technology': AppColors.warning,
    'people':     Color(0xFFEC4899),
  };

  static const _descs = {
    'general':    'General purpose document',
    'company':    'Company information & policies',
    'project':    'Project plans & updates',
    'technology': 'Technical documentation',
    'people':     'Team & personnel info',
  };

  @override
  Widget build(BuildContext context) {
    final color = _colors[type] ?? AppColors.primary;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: color.withValues(alpha: 0.2), width: 1),
        ),
        child: Row(children: [
          Container(
            width: 36, height: 36,
            decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(10)),
            child: Icon(_icons[type], color: color, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(type[0].toUpperCase() + type.substring(1),
                style: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600,
                    fontSize: 14, color: AppColors.textPrimary)),
              Text(_descs[type] ?? '', style: AppTextStyles.caption),
            ]),
          ),
          Icon(Icons.arrow_forward_ios_rounded, size: 14, color: color),
        ]),
      ),
    );
  }
}
