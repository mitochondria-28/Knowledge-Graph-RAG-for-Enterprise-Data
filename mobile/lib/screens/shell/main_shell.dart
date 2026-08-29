import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../core/theme/app_theme.dart';

class MainShell extends StatefulWidget {
  final Widget child;
  final int selectedIndex;
  final ValueChanged<int> onTabChanged;

  const MainShell({
    super.key,
    required this.child,
    required this.selectedIndex,
    required this.onTabChanged,
  });

  @override
  State<MainShell> createState() => _MainShellState();
}

class _NavItem {
  final IconData icon;
  final IconData activeIcon;
  final String label;
  const _NavItem({required this.icon, required this.activeIcon, required this.label});
}

const _navItems = [
  _NavItem(icon: Icons.home_outlined, activeIcon: Icons.home_rounded, label: 'Home'),
  _NavItem(icon: Icons.chat_bubble_outline_rounded, activeIcon: Icons.chat_bubble_rounded, label: 'Ask'),
  _NavItem(icon: Icons.folder_outlined, activeIcon: Icons.folder_rounded, label: 'Documents'),
  _NavItem(icon: Icons.person_outline_rounded, activeIcon: Icons.person_rounded, label: 'Profile'),
];

class _MainShellState extends State<MainShell> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: widget.child,
      extendBody: true,
      bottomNavigationBar: _FloatingNavBar(
        selectedIndex: widget.selectedIndex,
        onTap: widget.onTabChanged,
      ),
    );
  }
}

class _FloatingNavBar extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onTap;

  const _FloatingNavBar({required this.selectedIndex, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(28),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: Container(
            height: 68,
            decoration: BoxDecoration(
              color: AppColors.surface.withValues(alpha: 0.92),
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: AppColors.cardBorder.withValues(alpha: 0.8), width: 1),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.4),
                  blurRadius: 20,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: List.generate(_navItems.length, (i) {
                final item    = _navItems[i];
                final active  = selectedIndex == i;
                return Expanded(
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => onTap(i),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 250),
                          curve: Curves.easeInOutCubic,
                          width: active ? 48 : 32,
                          height: 32,
                          decoration: BoxDecoration(
                            color: active ? AppColors.primary.withValues(alpha: 0.18) : Colors.transparent,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Center(
                            child: Icon(
                              active ? item.activeIcon : item.icon,
                              size: 22,
                              color: active ? AppColors.primary : AppColors.textMuted,
                            ),
                          ),
                        ),
                        const SizedBox(height: 3),
                        AnimatedDefaultTextStyle(
                          duration: const Duration(milliseconds: 200),
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 10,
                            fontWeight: active ? FontWeight.w600 : FontWeight.w400,
                            color: active ? AppColors.primary : AppColors.textMuted,
                          ),
                          child: Text(item.label),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    ).animate().slideY(begin: 1, end: 0, duration: 400.ms, delay: 200.ms, curve: Curves.easeOutCubic);
  }
}
