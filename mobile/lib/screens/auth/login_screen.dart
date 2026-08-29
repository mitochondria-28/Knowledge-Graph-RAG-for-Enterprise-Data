import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:provider/provider.dart';
import '../../config/app_config.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/validators.dart';
import '../../core/widgets/app_text_field.dart';
import '../../core/widgets/gradient_button.dart';
import '../../providers/auth_provider.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with SingleTickerProviderStateMixin {
  final _formKey  = GlobalKey<FormState>();
  final _email    = TextEditingController();
  final _password = TextEditingController();
  bool _loading   = false;
  bool _googleLoading = false;
  late AnimationController _bgAnim;

  final _googleSignIn = GoogleSignIn(
    clientId: AppConfig.googleClientId,
    scopes: ['email', 'profile'],
  );

  @override
  void initState() {
    super.initState();
    _bgAnim = AnimationController(vsync: this, duration: const Duration(seconds: 12))..repeat();
    context.read<AuthProvider>().clearError();
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _bgAnim.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    final ok = await context.read<AuthProvider>().login(
      _email.text.trim(),
      _password.text,
    );
    if (mounted) {
      setState(() => _loading = false);
      if (ok) context.go('/home');
    }
  }

  Future<void> _googleLogin() async {
    setState(() => _googleLoading = true);
    try {
      final account = await _googleSignIn.signIn();
      if (account == null) { setState(() => _googleLoading = false); return; }
      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null) throw Exception('No ID token');
      if (!mounted) return;
      final ok = await context.read<AuthProvider>().loginWithGoogle(idToken);
      if (mounted) {
        setState(() => _googleLoading = false);
        if (ok) context.go('/home');
      }
    } catch (e) {
      if (mounted) setState(() => _googleLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth  = context.watch<AuthProvider>();
    final size  = MediaQuery.of(context).size;

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.splashGradient),
        child: Stack(
          children: [
            // Background orbs
            AnimatedBuilder(
              animation: _bgAnim,
              builder: (_, __) {
                final t = _bgAnim.value * 2 * math.pi;
                return Stack(children: [
                  Positioned(
                    top: -80 + math.sin(t) * 30,
                    left: -60 + math.cos(t) * 20,
                    child: _glow(260, AppColors.primary.withValues(alpha: 0.12)),
                  ),
                  Positioned(
                    bottom: -50 + math.cos(t * 0.8) * 25,
                    right: -40 + math.sin(t * 1.2) * 15,
                    child: _glow(220, AppColors.secondary.withValues(alpha: 0.08)),
                  ),
                ]);
              },
            ),

            // Content
            SafeArea(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: size.height - MediaQuery.of(context).padding.top),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SizedBox(height: size.height * 0.08),

                        // Logo + title
                        Center(
                          child: Container(
                            width: 72,
                            height: 72,
                            decoration: BoxDecoration(
                              gradient: AppColors.brandGradient,
                              borderRadius: BorderRadius.circular(20),
                              boxShadow: [BoxShadow(color: AppColors.primary.withValues(alpha: 0.4), blurRadius: 30)],
                            ),
                            child: const Icon(Icons.hub_rounded, size: 38, color: Colors.white),
                          ),
                        ).animate().scale(duration: 500.ms, curve: Curves.elasticOut),

                        const SizedBox(height: 24),

                        const Text(
                          'Welcome back',
                          textAlign: TextAlign.center,
                          style: AppTextStyles.displayMedium,
                        ).animate().fadeIn(delay: 200.ms).slideY(begin: 0.3, end: 0),

                        const SizedBox(height: 8),

                        const Text(
                          'Sign in to your knowledge base',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 14,
                            color: AppColors.textSecondary,
                          ),
                        ).animate().fadeIn(delay: 300.ms),

                        const SizedBox(height: 40),

                        // Error banner
                        if (auth.error != null)
                          Container(
                            margin: const EdgeInsets.only(bottom: 16),
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: AppColors.error.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: AppColors.error.withValues(alpha: 0.3)),
                            ),
                            child: Row(children: [
                              const Icon(Icons.error_outline_rounded, color: AppColors.error, size: 18),
                              const SizedBox(width: 10),
                              Expanded(child: Text(auth.error!, style: const TextStyle(color: AppColors.error, fontFamily: 'Inter', fontSize: 13))),
                            ]),
                          ).animate().fadeIn().shake(),

                        // Email field
                        AppTextField(
                          controller: _email,
                          label: 'Email address',
                          prefixIcon: Icons.email_outlined,
                          keyboardType: TextInputType.emailAddress,
                          validator: Validators.email,
                          textInputAction: TextInputAction.next,
                        ).animate().fadeIn(delay: 350.ms).slideY(begin: 0.2, end: 0),

                        const SizedBox(height: 16),

                        // Password field
                        AppTextField(
                          controller: _password,
                          label: 'Password',
                          prefixIcon: Icons.lock_outline_rounded,
                          obscureText: true,
                          validator: Validators.password,
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) => _login(),
                        ).animate().fadeIn(delay: 400.ms).slideY(begin: 0.2, end: 0),

                        const SizedBox(height: 28),

                        GradientButton(
                          label: 'Sign In',
                          isLoading: _loading,
                          onPressed: _loading ? null : _login,
                        ).animate().fadeIn(delay: 450.ms).slideY(begin: 0.2, end: 0),

                        const SizedBox(height: 20),

                        // Divider
                        Row(children: [
                          const Expanded(child: Divider(color: AppColors.cardBorder)),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16),
                            child: Text('or continue with', style: AppTextStyles.caption),
                          ),
                          const Expanded(child: Divider(color: AppColors.cardBorder)),
                        ]).animate().fadeIn(delay: 500.ms),

                        const SizedBox(height: 20),

                        // Google button
                        OutlinedGradientButton(
                          label: 'Sign in with Google',
                          onPressed: _googleLoading ? null : _googleLogin,
                          prefix: _googleLoading
                              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.textPrimary))
                              : _GoogleIcon(),
                        ).animate().fadeIn(delay: 550.ms),

                        const SizedBox(height: 32),

                        // Register link
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text("Don't have an account? ", style: AppTextStyles.bodyMedium),
                            GestureDetector(
                              onTap: () => context.go('/register'),
                              child: const Text(
                                'Create one',
                                style: TextStyle(
                                  fontFamily: 'Inter',
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                  color: AppColors.primaryLight,
                                ),
                              ),
                            ),
                          ],
                        ).animate().fadeIn(delay: 600.ms),

                        SizedBox(height: size.height * 0.06),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _glow(double size, Color color) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      gradient: RadialGradient(colors: [color, Colors.transparent]),
    ),
  );
}

class _GoogleIcon extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 20,
      height: 20,
      child: CustomPaint(painter: _GooglePainter()),
    );
  }
}

class _GooglePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final r = size.width / 2;

    // Simplified Google 'G' logo with colored segments
    final colors = [
      const Color(0xFF4285F4),
      const Color(0xFF34A853),
      const Color(0xFFFBBC05),
      const Color(0xFFEA4335),
    ];
    for (int i = 0; i < 4; i++) {
      final paint = Paint()
        ..color = colors[i]
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: r - 1.5),
        (-math.pi / 2) + (i * math.pi / 2),
        math.pi / 2 - 0.15,
        false,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_) => false;
}
