import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/validators.dart';
import '../../core/widgets/app_text_field.dart';
import '../../core/widgets/gradient_button.dart';
import '../../providers/auth_provider.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});
  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> with SingleTickerProviderStateMixin {
  final _formKey    = GlobalKey<FormState>();
  final _name       = TextEditingController();
  final _email      = TextEditingController();
  final _password   = TextEditingController();
  final _confirm    = TextEditingController();
  bool _loading     = false;
  late AnimationController _bgAnim;

  @override
  void initState() {
    super.initState();
    _bgAnim = AnimationController(vsync: this, duration: const Duration(seconds: 14))..repeat();
    context.read<AuthProvider>().clearError();
  }

  @override
  void dispose() {
    _name.dispose(); _email.dispose();
    _password.dispose(); _confirm.dispose();
    _bgAnim.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;
    if (_password.text != _confirm.text) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Passwords do not match'), backgroundColor: AppColors.error),
      );
      return;
    }
    setState(() => _loading = true);
    final ok = await context.read<AuthProvider>().register(
      _email.text.trim(),
      _password.text,
      _name.text.trim(),
    );
    if (mounted) {
      setState(() => _loading = false);
      if (ok) context.go('/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(gradient: AppColors.splashGradient),
        child: Stack(
          children: [
            AnimatedBuilder(
              animation: _bgAnim,
              builder: (_, __) {
                final t = _bgAnim.value * 2 * math.pi;
                return Stack(children: [
                  Positioned(
                    top: -100 + math.cos(t * 0.8) * 40,
                    right: -50 + math.sin(t) * 20,
                    child: Container(
                      width: 280, height: 280,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: RadialGradient(colors: [
                          AppColors.secondary.withValues(alpha: 0.12), Colors.transparent,
                        ]),
                      ),
                    ),
                  ),
                  Positioned(
                    bottom: -60 + math.sin(t * 0.7) * 30,
                    left: -30 + math.cos(t * 1.1) * 15,
                    child: Container(
                      width: 240, height: 240,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: RadialGradient(colors: [
                          AppColors.primary.withValues(alpha: 0.10), Colors.transparent,
                        ]),
                      ),
                    ),
                  ),
                ]);
              },
            ),

            SafeArea(
              child: Column(
                children: [
                  // Back button
                  Padding(
                    padding: const EdgeInsets.fromLTRB(8, 8, 0, 0),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: IconButton(
                        icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
                        color: AppColors.textSecondary,
                        onPressed: () => context.go('/login'),
                      ),
                    ),
                  ),

                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(horizontal: 28),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const SizedBox(height: 8),

                            const Text(
                              'Create account',
                              style: AppTextStyles.displayMedium,
                            ).animate().fadeIn(delay: 100.ms).slideY(begin: 0.3, end: 0),

                            const SizedBox(height: 8),

                            const Text(
                              'Build your private knowledge base',
                              style: TextStyle(fontFamily: 'Inter', fontSize: 14, color: AppColors.textSecondary),
                            ).animate().fadeIn(delay: 200.ms),

                            const SizedBox(height: 32),

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

                            AppTextField(
                              controller: _name,
                              label: 'Full name',
                              prefixIcon: Icons.person_outline_rounded,
                              validator: Validators.name,
                              textInputAction: TextInputAction.next,
                            ).animate().fadeIn(delay: 250.ms).slideY(begin: 0.2, end: 0),

                            const SizedBox(height: 14),

                            AppTextField(
                              controller: _email,
                              label: 'Email address',
                              prefixIcon: Icons.email_outlined,
                              keyboardType: TextInputType.emailAddress,
                              validator: Validators.email,
                              textInputAction: TextInputAction.next,
                            ).animate().fadeIn(delay: 300.ms).slideY(begin: 0.2, end: 0),

                            const SizedBox(height: 14),

                            AppTextField(
                              controller: _password,
                              label: 'Password',
                              prefixIcon: Icons.lock_outline_rounded,
                              obscureText: true,
                              validator: Validators.password,
                              textInputAction: TextInputAction.next,
                            ).animate().fadeIn(delay: 350.ms).slideY(begin: 0.2, end: 0),

                            const SizedBox(height: 14),

                            AppTextField(
                              controller: _confirm,
                              label: 'Confirm password',
                              prefixIcon: Icons.lock_outline_rounded,
                              obscureText: true,
                              validator: (v) {
                                if (v == null || v.isEmpty) return 'Please confirm your password';
                                if (v != _password.text) return 'Passwords do not match';
                                return null;
                              },
                              textInputAction: TextInputAction.done,
                              onSubmitted: (_) => _register(),
                            ).animate().fadeIn(delay: 400.ms).slideY(begin: 0.2, end: 0),

                            const SizedBox(height: 10),

                            // Password requirements hint
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: AppColors.info.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(10),
                                border: Border.all(color: AppColors.info.withValues(alpha: 0.2)),
                              ),
                              child: const Row(children: [
                                Icon(Icons.info_outline_rounded, color: AppColors.info, size: 16),
                                SizedBox(width: 8),
                                Text('Password must be at least 8 characters',
                                  style: TextStyle(fontFamily: 'Inter', fontSize: 12, color: AppColors.textSecondary)),
                              ]),
                            ).animate().fadeIn(delay: 430.ms),

                            const SizedBox(height: 28),

                            GradientButton(
                              label: 'Create Account',
                              isLoading: _loading,
                              onPressed: _loading ? null : _register,
                            ).animate().fadeIn(delay: 480.ms).slideY(begin: 0.2, end: 0),

                            const SizedBox(height: 28),

                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text('Already have an account? ', style: AppTextStyles.bodyMedium),
                                GestureDetector(
                                  onTap: () => context.go('/login'),
                                  child: const Text('Sign in',
                                    style: TextStyle(fontFamily: 'Inter', fontSize: 14,
                                        fontWeight: FontWeight.w600, color: AppColors.primaryLight)),
                                ),
                              ],
                            ).animate().fadeIn(delay: 530.ms),

                            const SizedBox(height: 40),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
