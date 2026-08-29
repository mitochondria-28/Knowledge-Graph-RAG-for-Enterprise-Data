import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/glass_card.dart';
import '../../providers/auth_provider.dart';
import '../../providers/document_provider.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final docs = context.watch<DocumentProvider>();
    final user = auth.user;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 120),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Profile', style: AppTextStyles.displayMedium)
                  .animate().fadeIn(duration: 300.ms),
              const SizedBox(height: 28),

              // Avatar card
              GlassCard(
                padding: const EdgeInsets.all(24),
                borderRadius: 24,
                child: Row(
                  children: [
                    Container(
                      width: 72, height: 72,
                      decoration: BoxDecoration(
                        gradient: AppColors.brandGradient,
                        shape: BoxShape.circle,
                        boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.4), blurRadius: 24)],
                      ),
                      child: Center(
                        child: Text(
                          user?.initials ?? 'U',
                          style: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700,
                              fontSize: 26, color: Colors.white),
                        ),
                      ),
                    ),
                    const SizedBox(width: 18),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(user?.name ?? '', style: AppTextStyles.headingLarge,
                              maxLines: 1, overflow: TextOverflow.ellipsis),
                          const SizedBox(height: 4),
                          Text(user?.email ?? '', style: AppTextStyles.bodyMedium,
                              maxLines: 1, overflow: TextOverflow.ellipsis),
                          const SizedBox(height: 10),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                            decoration: BoxDecoration(
                              gradient: AppColors.brandGradient,
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: const Text('Pro Account', style: TextStyle(fontFamily: 'Inter',
                                fontSize: 11, fontWeight: FontWeight.w600, color: Colors.white)),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ).animate().fadeIn(delay: 100.ms).slideY(begin: 0.2, end: 0),

              const SizedBox(height: 20),

              // Stats
              Row(
                children: [
                  Expanded(child: _StatTile(
                    icon: Icons.folder_rounded,
                    color: AppColors.secondary,
                    label: 'Documents',
                    value: '${docs.documents.length}',
                  )),
                  const SizedBox(width: 12),
                  Expanded(child: _StatTile(
                    icon: Icons.hub_rounded,
                    color: AppColors.primary,
                    label: 'Mode',
                    value: 'KG',
                  )),
                  const SizedBox(width: 12),
                  Expanded(child: _StatTile(
                    icon: Icons.verified_rounded,
                    color: AppColors.accent,
                    label: 'Citations',
                    value: 'On',
                  )),
                ],
              ).animate().fadeIn(delay: 180.ms),

              const SizedBox(height: 28),
              const Text('Account', style: AppTextStyles.label),
              const SizedBox(height: 12),

              _Section(items: [
                _MenuItem(
                  icon: Icons.person_outline_rounded,
                  label: 'Edit Profile',
                  color: AppColors.primary,
                  onTap: () => _comingSoon(context),
                ),
                _MenuItem(
                  icon: Icons.lock_outline_rounded,
                  label: 'Change Password',
                  color: AppColors.secondary,
                  onTap: () => _comingSoon(context),
                ),
                _MenuItem(
                  icon: Icons.notifications_none_rounded,
                  label: 'Notifications',
                  color: AppColors.warning,
                  onTap: () => _comingSoon(context),
                ),
              ]).animate().fadeIn(delay: 250.ms),

              const SizedBox(height: 20),
              const Text('Knowledge Base', style: AppTextStyles.label),
              const SizedBox(height: 12),

              _Section(items: [
                _MenuItem(
                  icon: Icons.folder_outlined,
                  label: 'My Documents (${docs.documents.length})',
                  color: AppColors.accent,
                  onTap: () => context.go('/documents'),
                ),
                _MenuItem(
                  icon: Icons.info_outline_rounded,
                  label: 'API Status',
                  color: AppColors.info,
                  onTap: () => _showApiStatus(context),
                ),
              ]).animate().fadeIn(delay: 300.ms),

              const SizedBox(height: 20),
              const Text('App', style: AppTextStyles.label),
              const SizedBox(height: 12),

              _Section(items: [
                _MenuItem(
                  icon: Icons.help_outline_rounded,
                  label: 'Help & Support',
                  color: AppColors.secondary,
                  onTap: () => _comingSoon(context),
                ),
                _MenuItem(
                  icon: Icons.info_outline_rounded,
                  label: 'About KG-RAG',
                  color: AppColors.primary,
                  onTap: () => _showAbout(context),
                ),
              ]).animate().fadeIn(delay: 350.ms),

              const SizedBox(height: 20),

              // Sign out
              GestureDetector(
                onTap: () => _confirmLogout(context),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: AppColors.error.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.error.withValues(alpha: 0.25), width: 1),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.logout_rounded, color: AppColors.error, size: 18),
                      SizedBox(width: 10),
                      Text('Sign Out', style: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600,
                          fontSize: 15, color: AppColors.error)),
                    ],
                  ),
                ),
              ).animate().fadeIn(delay: 400.ms),

              const SizedBox(height: 12),
              Center(
                child: Text('KG-RAG v1.0.0 · Enterprise Edition',
                  style: AppTextStyles.caption),
              ).animate().fadeIn(delay: 450.ms),
            ],
          ),
        ),
      ),
    );
  }

  void _comingSoon(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Coming soon!'), duration: Duration(seconds: 1)),
    );
  }

  void _showAbout(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.card,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('About KG-RAG', style: AppTextStyles.headingLarge),
        content: const Text(
          'Enterprise Knowledge Graph RAG\n\n'
          'Multi-hop AI that traverses knowledge graphs to answer complex questions about your documents.\n\n'
          'Every answer is validated against source text — no hallucinations.',
          style: TextStyle(fontFamily: 'Inter', fontSize: 13, color: AppColors.textSecondary, height: 1.6),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close', style: TextStyle(color: AppColors.primary)),
          ),
        ],
      ),
    );
  }

  void _showApiStatus(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.card,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('API Info', style: AppTextStyles.headingLarge),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _ApiRow(label: 'Backend', value: 'enterprise-kg-rag.vercel.app'),
            const SizedBox(height: 8),
            _ApiRow(label: 'Model', value: 'Gemini 2.5 Flash'),
            const SizedBox(height: 8),
            _ApiRow(label: 'Auth', value: 'JWT Bearer'),
            const SizedBox(height: 8),
            _ApiRow(label: 'Storage', value: 'PostgreSQL'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close', style: TextStyle(color: AppColors.primary)),
          ),
        ],
      ),
    );
  }

  void _confirmLogout(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.card,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Sign Out', style: AppTextStyles.headingLarge),
        content: const Text('Are you sure you want to sign out?',
          style: TextStyle(fontFamily: 'Inter', fontSize: 14, color: AppColors.textSecondary)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel', style: TextStyle(color: AppColors.textSecondary)),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              context.read<AuthProvider>().logout();
              context.go('/login');
            },
            child: const Text('Sign Out', style: TextStyle(color: AppColors.error)),
          ),
        ],
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String label;
  final String value;

  const _StatTile({required this.icon, required this.color, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.2), width: 1),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700,
              fontSize: 18, color: color)),
          const SizedBox(height: 2),
          Text(label, style: AppTextStyles.caption, textAlign: TextAlign.center,
              maxLines: 1, overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final List<_MenuItem> items;
  const _Section({required this.items});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.cardBorder, width: 1),
      ),
      child: Column(
        children: items.asMap().entries.map((e) {
          final isLast = e.key == items.length - 1;
          return Column(
            children: [
              e.value,
              if (!isLast) const Divider(height: 1, indent: 56, color: AppColors.cardBorder),
            ],
          );
        }).toList(),
      ),
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _MenuItem({required this.icon, required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          child: Row(children: [
            Container(
              width: 36, height: 36,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: color, size: 18),
            ),
            const SizedBox(width: 14),
            Expanded(child: Text(label, style: AppTextStyles.bodyLarge)),
            const Icon(Icons.arrow_forward_ios_rounded, size: 14, color: AppColors.textMuted),
          ]),
        ),
      ),
    );
  }
}

class _ApiRow extends StatelessWidget {
  final String label;
  final String value;
  const _ApiRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(width: 70, child: Text(label, style: AppTextStyles.caption)),
        Expanded(
          child: Text(value, style: const TextStyle(fontFamily: 'Inter', fontSize: 12,
              color: AppColors.textPrimary, fontWeight: FontWeight.w500)),
        ),
      ],
    );
  }
}
