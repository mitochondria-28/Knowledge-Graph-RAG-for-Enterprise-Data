import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class AppTextField extends StatefulWidget {
  final TextEditingController controller;
  final String label;
  final String? hint;
  final IconData? prefixIcon;
  final Widget? suffix;
  final bool obscureText;
  final TextInputType keyboardType;
  final String? Function(String?)? validator;
  final void Function(String)? onChanged;
  final int maxLines;
  final bool autofocus;
  final TextInputAction? textInputAction;
  final void Function(String)? onSubmitted;

  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.prefixIcon,
    this.suffix,
    this.obscureText = false,
    this.keyboardType = TextInputType.text,
    this.validator,
    this.onChanged,
    this.maxLines = 1,
    this.autofocus = false,
    this.textInputAction,
    this.onSubmitted,
  });

  @override
  State<AppTextField> createState() => _AppTextFieldState();
}

class _AppTextFieldState extends State<AppTextField> {
  bool _isFocused = false;
  bool _showText = false;

  @override
  Widget build(BuildContext context) {
    final isPassword = widget.obscureText;

    return Focus(
      onFocusChange: (v) => setState(() => _isFocused = v),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          boxShadow: _isFocused
              ? [
                  BoxShadow(
                    color: AppColors.primary.withValues(alpha: 0.15),
                    blurRadius: 16,
                    offset: const Offset(0, 4),
                  ),
                ]
              : [],
        ),
        child: TextFormField(
          controller: widget.controller,
          obscureText: isPassword && !_showText,
          keyboardType: widget.keyboardType,
          validator: widget.validator,
          onChanged: widget.onChanged,
          maxLines: isPassword ? 1 : widget.maxLines,
          autofocus: widget.autofocus,
          textInputAction: widget.textInputAction,
          onFieldSubmitted: widget.onSubmitted,
          style: AppTextStyles.bodyLarge,
          decoration: InputDecoration(
            labelText: widget.label,
            hintText: widget.hint,
            prefixIcon: widget.prefixIcon != null
                ? Icon(widget.prefixIcon, size: 20, color: _isFocused ? AppColors.primary : AppColors.textMuted)
                : null,
            suffixIcon: isPassword
                ? IconButton(
                    icon: Icon(
                      _showText ? Icons.visibility_off_rounded : Icons.visibility_rounded,
                      size: 20,
                      color: AppColors.textMuted,
                    ),
                    onPressed: () => setState(() => _showText = !_showText),
                  )
                : widget.suffix,
          ),
        ),
      ),
    );
  }
}
