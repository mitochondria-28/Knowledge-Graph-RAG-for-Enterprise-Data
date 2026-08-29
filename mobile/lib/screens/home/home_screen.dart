import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/glass_card.dart';
import '../../providers/auth_provider.dart';
import '../../providers/document_provider.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with SingleTickerProviderStateMixin {
  late AnimationController _bgAnim;

  @override
  void initState() {
    super.initState();
    _bgAnim = AnimationController(vsync: this, duration: const Duration(seconds: 12))..repeat();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DocumentProvider>().fetchDocuments();
    });
  }

  @override
  void dispose() {
    _bgAnim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final docs = context.watch<DocumentProvider>();
    final user = auth.user;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Stack(
        children: [
          // Animated bg
          AnimatedBuilder(
            animation: _bgAnim,
            builder: (_, __) {
              final t = _bgAnim.value * 2 * math.pi;
              return Positioned(
                top: -100 + math.sin(t) * 30,
                right: -80 + math.cos(t * 0.7) * 20,
                child: Container(
                  width: 300, height: 300,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(colors: [
                      AppColors.primary.withValues(alpha: 0.10), Colors.transparent,
                    ]),
                  ),
                ),
              );
            },
          ),

          SafeArea(
            bottom: false,
            child: CustomScrollView(
              slivers: [
                // App bar
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _greeting(),
                                style: AppTextStyles.bodyMedium,
                              ),
                              const SizedBox(height: 2),
                              Text(
                                user?.name ?? 'Researcher',
                                style: AppTextStyles.displayMedium,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                        _Avatar(user: user),
                      ],
                    ),
                  ).animate().fadeIn(duration: 400.ms),
                ),

                SliverToBoxAdapter(child: const SizedBox(height: 28)),

                // Hero card — Ask anything
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: _HeroAskCard(onTap: () => context.go('/ask')),
                  ).animate().fadeIn(delay: 150.ms).slideY(begin: 0.2, end: 0),
                ),

                SliverToBoxAdapter(child: const SizedBox(height: 24)),

                // Stats row
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Row(
                      children: [
                        Expanded(
                          child: _StatCard(
                            icon: Icons.folder_rounded,
                            color: AppColors.secondary,
                            label: 'Documents',
                            value: docs.documents.length.toString(),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _StatCard(
                            icon: Icons.hub_rounded,
                            color: AppColors.primary,
                            label: 'Graph Type',
                            value: 'KG-RAG',
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _StatCard(
                            icon: Icons.verified_rounded,
                            color: AppColors.accent,
                            label: 'Citations',
                            value: 'Verified',
                          ),
                        ),
                      ],
                    ),
                  ).animate().fadeIn(delay: 250.ms),
                ),

                SliverToBoxAdapter(child: const SizedBox(height: 28)),

                // Quick actions
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Quick Actions', style: AppTextStyles.headingMedium),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(
                              child: _QuickAction(
                                icon: Icons.upload_file_rounded,
                                label: 'Upload Doc',
                                color: AppColors.secondary,
                                onTap: () => context.go('/documents'),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _QuickAction(
                                icon: Icons.chat_bubble_rounded,
                                label: 'Ask AI',
                                color: AppColors.primary,
                                onTap: () => context.go('/ask'),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _QuickAction(
                                icon: Icons.list_alt_rounded,
                                label: 'My Docs',
                                color: AppColors.accent,
                                onTap: () => context.go('/documents'),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ).animate().fadeIn(delay: 300.ms),
                ),

                SliverToBoxAdapter(child: const SizedBox(height: 28)),

                // Recent documents
                if (docs.documents.isNotEmpty) ...[
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Recent Documents', style: AppTextStyles.headingMedium),
                          GestureDetector(
                            onTap: () => context.go('/documents'),
                            child: const Text('See all',
                              style: TextStyle(fontFamily: 'Inter', fontSize: 13,
                                  fontWeight: FontWeight.w500, color: AppColors.primaryLight)),
                          ),
                        ],
                      ),
                    ).animate().fadeIn(delay: 350.ms),
                  ),
                  SliverToBoxAdapter(child: const SizedBox(height: 12)),
                  SliverList(
                    delegate: SliverChildBuilderDelegate(
                      (context, i) {
                        final doc = docs.documents[i];
                        return Padding(
                          padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
                          child: _RecentDocTile(doc: doc),
                        ).animate().fadeIn(delay: Duration(milliseconds: 380 + i * 60))
                            .slideX(begin: 0.15, end: 0);
                      },
                      childCount: math.min(docs.documents.length, 5),
                    ),
                  ),
                ] else if (!docs.isLoading) ...[
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      child: _EmptyDocsHint(onTap: () => context.go('/documents')),
                    ).animate().fadeIn(delay: 350.ms),
                  ),
                ],

                const SliverToBoxAdapter(child: SizedBox(height: 120)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning,';
    if (h < 17) return 'Good afternoon,';
    return 'Good evening,';
  }
}

// ── Sub-widgets ─────────────────────────────────────────────────────────────

class _Avatar extends StatelessWidget {
  final dynamic user;
  const _Avatar({this.user});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 48, height: 48,
      decoration: BoxDecoration(
        gradient: AppColors.brandGradient,
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.cardBorder, width: 2),
      ),
      child: Center(
        child: Text(
          user?.initials ?? 'U',
          style: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700,
              fontSize: 16, color: Colors.white),
        ),
      ),
    );
  }
}

class _HeroAskCard extends StatelessWidget {
  final VoidCallback onTap;
  const _HeroAskCard({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 120,
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF3B1E7A), Color(0xFF0E4F6A), Color(0xFF0A3040)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: AppColors.primary.withValues(alpha: 0.3), width: 1),
          boxShadow: [
            BoxShadow(color: AppColors.primary.withValues(alpha: 0.2), blurRadius: 24, offset: const Offset(0, 8)),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text('Ask your knowledge base',
                      style: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700,
                          fontSize: 17, color: Colors.white)),
                    const SizedBox(height: 6),
                    Text('Multi-hop graph intelligence',
                      style: TextStyle(fontFamily: 'Inter', fontSize: 12,
                          color: Colors.white.withValues(alpha: 0.6))),
                  ],
                ),
              ),
              Container(
                width: 48, height: 48,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(Icons.arrow_forward_rounded, color: Colors.white, size: 22),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String label;
  final String value;

  const _StatCard({required this.icon, required this.color, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      borderRadius: 16,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 36, height: 36,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: color, size: 18),
          ),
          const SizedBox(height: 10),
          Text(value, style: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700,
              fontSize: 18, color: AppColors.textPrimary)),
          const SizedBox(height: 2),
          Text(label, style: AppTextStyles.caption, maxLines: 1, overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _QuickAction({required this.icon, required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withValues(alpha: 0.25), width: 1),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 26),
            const SizedBox(height: 8),
            Text(label, style: TextStyle(fontFamily: 'Inter', fontSize: 11,
                fontWeight: FontWeight.w500, color: color), textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _RecentDocTile extends StatelessWidget {
  final dynamic doc;
  const _RecentDocTile({required this.doc});

  @override
  Widget build(BuildContext context) {
    final ext = doc.extension ?? '';
    return GlassCard(
      padding: const EdgeInsets.all(14),
      borderRadius: 14,
      child: Row(
        children: [
          _ExtIcon(ext: ext),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(doc.filename ?? '', style: AppTextStyles.headingMedium,
                    maxLines: 1, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 3),
                Row(children: [
                  _Tag(label: doc.typeLabel ?? 'General'),
                  if (doc.displaySize != null && doc.displaySize.isNotEmpty) ...[
                    const SizedBox(width: 6),
                    Text(doc.displaySize, style: AppTextStyles.caption),
                  ],
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ExtIcon extends StatelessWidget {
  final String ext;
  const _ExtIcon({required this.ext});

  @override
  Widget build(BuildContext context) {
    Color color;
    IconData icon;
    switch (ext) {
      case '.pdf': color = AppColors.error; icon = Icons.picture_as_pdf_rounded; break;
      case '.md':  color = AppColors.secondary; icon = Icons.description_rounded; break;
      default:     color = AppColors.accent; icon = Icons.article_rounded;
    }
    return Container(
      width: 40, height: 40,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Icon(icon, color: color, size: 20),
    );
  }
}

class _Tag extends StatelessWidget {
  final String label;
  const _Tag({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: const TextStyle(fontFamily: 'Inter', fontSize: 10,
          fontWeight: FontWeight.w500, color: AppColors.primaryLight)),
    );
  }
}

class _EmptyDocsHint extends StatelessWidget {
  final VoidCallback onTap;
  const _EmptyDocsHint({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(28),
      borderRadius: 20,
      child: Column(
        children: [
          Container(
            width: 64, height: 64,
            decoration: BoxDecoration(
              color: AppColors.secondary.withValues(alpha: 0.12),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.upload_file_rounded, color: AppColors.secondary, size: 32),
          ),
          const SizedBox(height: 16),
          const Text('No documents yet', style: AppTextStyles.headingMedium),
          const SizedBox(height: 8),
          Text('Upload your first document to start\nasking intelligent questions about it.',
            textAlign: TextAlign.center,
            style: AppTextStyles.bodyMedium),
          const SizedBox(height: 20),
          GestureDetector(
            onTap: onTap,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              decoration: BoxDecoration(
                gradient: AppColors.brandGradient,
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Text('Upload Document',
                style: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600,
                    fontSize: 13, color: Colors.white)),
            ),
          ),
        ],
      ),
    );
  }
}
