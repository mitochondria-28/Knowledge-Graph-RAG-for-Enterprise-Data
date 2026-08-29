import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../theme/app_theme.dart';

class GradientButton extends StatefulWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final Gradient? gradient;
  final Widget? prefix;
  final double height;
  final double? width;
  final double borderRadius;

  const GradientButton({
    super.key,
    required this.label,
    this.onPressed,
    this.isLoading = false,
    this.gradient,
    this.prefix,
    this.height = 56,
    this.width,
    this.borderRadius = 14,
  });

  @override
  State<GradientButton> createState() => _GradientButtonState();
}

class _GradientButtonState extends State<GradientButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onPressed?.call();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: _pressed ? 0.97 : 1.0,
        duration: const Duration(milliseconds: 100),
        child: Container(
          height: widget.height,
          width: widget.width,
          decoration: BoxDecoration(
            gradient: widget.onPressed == null
                ? const LinearGradient(
                    colors: [Color(0xFF3A3A50), Color(0xFF2A2A40)],
                  )
                : (widget.gradient ?? AppColors.brandGradient),
            borderRadius: BorderRadius.circular(widget.borderRadius),
            boxShadow: widget.onPressed == null
                ? []
                : [
                    BoxShadow(
                      color: AppColors.primary.withValues(alpha: 0.35),
                      blurRadius: 20,
                      offset: const Offset(0, 8),
                    ),
                  ],
          ),
          child: Center(
            child: widget.isLoading
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.5,
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  )
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (widget.prefix != null) ...[
                        widget.prefix!,
                        const SizedBox(width: 10),
                      ],
                      Text(
                        widget.label,
                        style: const TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                          letterSpacing: 0.3,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    ).animate().fadeIn(duration: 300.ms);
  }
}

// ── Outlined Button variant ─────────────────────────────────────────────────
class OutlinedGradientButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final Widget? prefix;
  final double height;

  const OutlinedGradientButton({
    super.key,
    required this.label,
    this.onPressed,
    this.prefix,
    this.height = 56,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onPressed,
      child: Container(
        height: height,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.cardBorder, width: 1.5),
          color: AppColors.card,
        ),
        child: Center(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (prefix != null) ...[
                prefix!,
                const SizedBox(width: 10),
              ],
              Text(
                label,
                style: const TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                  color: AppColors.textPrimary,
                  letterSpacing: 0.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
