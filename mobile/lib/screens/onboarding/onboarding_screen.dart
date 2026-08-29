import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/gradient_button.dart';

class _OnboardPage {
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  const _OnboardPage({required this.icon, required this.color, required this.title, required this.subtitle});
}

const _pages = [
  _OnboardPage(
    icon: Icons.hub_rounded,
    color: AppColors.primary,
    title: 'Knowledge Graph\nIntelligence',
    subtitle: 'Ask complex questions across your documents. Our AI traverses multi-hop relationships to find answers a simple search would miss.',
  ),
  _OnboardPage(
    icon: Icons.upload_file_rounded,
    color: AppColors.secondary,
    title: 'Your Private\nKnowledge Base',
    subtitle: 'Upload PDFs, Markdown, and text files. Every document is privately isolated — only you can query your data.',
  ),
  _OnboardPage(
    icon: Icons.verified_rounded,
    color: AppColors.accent,
    title: 'Verified Citations\nEvery Time',
    subtitle: 'Every answer includes citations validated against the source text. No hallucinations, no guesses — just verified intelligence.',
  ),
];

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});
  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen>
    with TickerProviderStateMixin {
  final _pageController = PageController();
  int _current = 0;
  late AnimationController _bgController;

  @override
  void initState() {
    super.initState();
    _bgController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..repeat();
  }

  @override
  void dispose() {
    _pageController.dispose();
    _bgController.dispose();
    super.dispose();
  }

  void _next() {
    if (_current < _pages.length - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOutCubic,
      );
    } else {
      context.go('/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final page = _pages[_current];

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.splashGradient),
        child: SafeArea(
          child: Column(
            children: [
              // Skip button
              Align(
                alignment: Alignment.centerRight,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(0, 16, 20, 0),
                  child: TextButton(
                    onPressed: () => context.go('/login'),
                    child: Text(
                      _current < _pages.length - 1 ? 'Skip' : '',
                      style: AppTextStyles.bodyMedium,
                    ),
                  ),
                ),
              ),

              // Page content
              Expanded(
                child: PageView.builder(
                  controller: _pageController,
                  itemCount: _pages.length,
                  onPageChanged: (i) => setState(() => _current = i),
                  itemBuilder: (context, index) {
                    final p = _pages[index];
                    return _OnboardPageView(page: p, size: size, bgAnim: _bgController);
                  },
                ),
              ),

              // Dots + button
              Padding(
                padding: const EdgeInsets.fromLTRB(28, 0, 28, 40),
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: List.generate(_pages.length, (i) {
                        return AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          margin: const EdgeInsets.symmetric(horizontal: 4),
                          width: _current == i ? 24 : 8,
                          height: 8,
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(4),
                            color: _current == i ? page.color : AppColors.textMuted,
                          ),
                        );
                      }),
                    ),
                    const SizedBox(height: 32),
                    GradientButton(
                      label: _current < _pages.length - 1 ? 'Continue' : 'Get Started',
                      onPressed: _next,
                      gradient: LinearGradient(
                        colors: [page.color, page.color.withValues(alpha: 0.7)],
                        begin: Alignment.centerLeft,
                        end: Alignment.centerRight,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OnboardPageView extends StatelessWidget {
  final _OnboardPage page;
  final Size size;
  final AnimationController bgAnim;

  const _OnboardPageView({required this.page, required this.size, required this.bgAnim});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 28),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Animated icon container
          AnimatedBuilder(
            animation: bgAnim,
            builder: (_, child) {
              final t = bgAnim.value * 2 * math.pi;
              return Transform.translate(
                offset: Offset(math.sin(t) * 8, math.cos(t * 0.7) * 6),
                child: child,
              );
            },
            child: Container(
              width: 140,
              height: 140,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    page.color.withValues(alpha: 0.25),
                    page.color.withValues(alpha: 0.05),
                  ],
                ),
                border: Border.all(
                  color: page.color.withValues(alpha: 0.4),
                  width: 1.5,
                ),
              ),
              child: Center(
                child: Icon(page.icon, size: 64, color: page.color),
              ),
            ),
          ).animate().scale(duration: 600.ms, curve: Curves.elasticOut),

          const SizedBox(height: 48),

          Text(
            page.title,
            textAlign: TextAlign.center,
            style: AppTextStyles.displayLarge.copyWith(height: 1.15),
          ).animate().fadeIn(delay: 200.ms).slideY(begin: 0.3, end: 0),

          const SizedBox(height: 20),

          Text(
            page.subtitle,
            textAlign: TextAlign.center,
            style: AppTextStyles.bodyLarge.copyWith(color: AppColors.textSecondary),
          ).animate().fadeIn(delay: 350.ms).slideY(begin: 0.2, end: 0),
        ],
      ),
    );
  }
}
