import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'core/theme/app_theme.dart';
import 'providers/auth_provider.dart';
import 'providers/document_provider.dart';
import 'providers/ask_provider.dart';
import 'screens/splash/splash_screen.dart';
import 'screens/onboarding/onboarding_screen.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/register_screen.dart';
import 'screens/shell/main_shell.dart';
import 'screens/home/home_screen.dart';
import 'screens/ask/ask_screen.dart';
import 'screens/documents/documents_screen.dart';
import 'screens/profile/profile_screen.dart';

// ── Route indices for the shell ─────────────────────────────────────────────
const _tabRoutes = ['/home', '/ask', '/documents', '/profile'];

int _indexFor(String location) {
  for (int i = 0; i < _tabRoutes.length; i++) {
    if (location.startsWith(_tabRoutes[i])) return i;
  }
  return 0;
}

// ── Router ──────────────────────────────────────────────────────────────────
GoRouter buildRouter(AuthProvider auth) => GoRouter(
  initialLocation: '/splash',
  redirect: (context, state) {
    final loc = state.matchedLocation;
    // Let splash handle its own auth check
    if (loc == '/splash') return null;
    // Block shell routes for unauthenticated users
    final authenticated = auth.status == AuthStatus.authenticated;
    final onAuth = loc == '/login' || loc == '/register' || loc == '/onboarding';
    if (!authenticated && !onAuth) return '/login';
    if (authenticated && onAuth) return '/home';
    return null;
  },
  refreshListenable: auth,
  routes: [
    GoRoute(path: '/splash',    builder: (_, __) => const SplashScreen()),
    GoRoute(path: '/onboarding',builder: (_, __) => const OnboardingScreen()),
    GoRoute(path: '/login',     builder: (_, __) => const LoginScreen()),
    GoRoute(path: '/register',  builder: (_, __) => const RegisterScreen()),

    // Shell routes (bottom nav)
    ShellRoute(
      builder: (context, state, child) {
        final idx = _indexFor(state.matchedLocation);
        return MainShell(
          selectedIndex: idx,
          onTabChanged: (i) => context.go(_tabRoutes[i]),
          child: child,
        );
      },
      routes: [
        GoRoute(path: '/home',      builder: (_, __) => const HomeScreen()),
        GoRoute(path: '/ask',       builder: (_, __) => const AskScreen()),
        GoRoute(path: '/documents', builder: (_, __) => const DocumentsScreen()),
        GoRoute(path: '/profile',   builder: (_, __) => const ProfileScreen()),
      ],
    ),
  ],
);

// ── App root ────────────────────────────────────────────────────────────────
class KgRagApp extends StatelessWidget {
  const KgRagApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => DocumentProvider()),
        ChangeNotifierProvider(create: (_) => AskProvider()),
      ],
      child: Builder(
        builder: (context) {
          final auth = context.watch<AuthProvider>();
          return MaterialApp.router(
            title: 'KG-RAG',
            debugShowCheckedModeBanner: false,
            theme: AppTheme.dark,
            routerConfig: buildRouter(auth),
          );
        },
      ),
    );
  }
}
