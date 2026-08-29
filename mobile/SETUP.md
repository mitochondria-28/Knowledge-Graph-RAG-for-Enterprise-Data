# KG-RAG Mobile — Setup Guide

Flutter app for the Enterprise KG-RAG backend at `https://enterprise-kg-rag.vercel.app`.

## Prerequisites

- Flutter SDK ≥ 3.22 (`flutter --version`)
- Dart SDK ≥ 3.3 (bundled with Flutter)
- For Android: Android Studio + Android SDK 26+
- For iOS: Xcode 15+ (macOS only)

## 1. Install dependencies

```bash
cd mobile
flutter pub get
```

## 2. Add Inter font files

Download Inter from https://rsms.me/inter/ and place these files in `assets/fonts/`:
```
assets/fonts/Inter-Regular.ttf
assets/fonts/Inter-Medium.ttf
assets/fonts/Inter-SemiBold.ttf
assets/fonts/Inter-Bold.ttf
```

Alternatively, replace the font family with `Roboto` in `lib/core/theme/app_theme.dart`
(just remove the `fontFamily: 'Inter'` lines — Roboto ships with Flutter).

## 3. Google Sign-In setup (optional)

Google Sign-In requires platform-specific configuration.

### Android

1. Go to https://console.cloud.google.com/apis/credentials
2. Create an **Android** OAuth 2.0 Client ID
3. Set Package name: `com.enterprise.kg_rag`
4. Add your debug SHA-1 fingerprint:
   ```bash
   keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android
   ```
5. Download `google-services.json` and place at `android/app/google-services.json`
6. Add to `android/app/build.gradle` under `apply plugin` lines:
   ```groovy
   apply plugin: 'com.google.gms.google-services'
   ```
7. Add to `android/build.gradle` dependencies:
   ```groovy
   classpath 'com.google.gms:google-services:4.4.1'
   ```

### iOS

The `ios/Runner/Info.plist` already has the Google Client ID set.
Replace with your own iOS Client ID from Google Cloud Console.

## 4. Run the app

```bash
# List connected devices
flutter devices

# Run on Android emulator / device
flutter run

# Run on iOS simulator (macOS only)
open -a Simulator
flutter run

# Run with a specific device
flutter run -d <device-id>
```

## 5. Build for release

```bash
# Android APK
flutter build apk --release

# Android App Bundle (for Play Store)
flutter build appbundle --release

# iOS (macOS only)
flutter build ipa
```

## Architecture

```
lib/
├── main.dart             Entry point
├── app.dart              Router + providers
├── config/               API base URL, constants
├── core/
│   ├── theme/            Colors, text styles, ThemeData
│   ├── utils/            Form validators
│   └── widgets/          Reusable: GlassCard, GradientButton, TextField, Shimmer
├── models/               UserModel, DocumentModel, AskModel, ChatMessage
├── services/             ApiClient (Dio), AuthService, DocumentService, AskService
├── providers/            AuthProvider, DocumentProvider, AskProvider
└── screens/
    ├── splash/           Animated splash with orbs
    ├── onboarding/       3-page intro with page indicator
    ├── auth/             Login + Register (Google OAuth included)
    ├── shell/            Floating glassmorphism bottom nav
    ├── home/             Dashboard, stats, recent docs, hero card
    ├── ask/              Chat interface, typing indicator, citation cards
    ├── documents/        Document list, upload with progress, empty state
    └── profile/          User info, stats, settings, logout
```

## Features implemented

| Feature | Status |
|---------|--------|
| Email/password auth | ✅ |
| Google OAuth login | ✅ |
| JWT session persistence | ✅ |
| Document upload (PDF/MD/TXT) | ✅ |
| Upload progress bar | ✅ |
| Document type categorization | ✅ |
| Document list with pull-to-refresh | ✅ |
| AI Q&A with graph/vector/hybrid routing | ✅ |
| Chat interface with history | ✅ |
| Typing indicator animation | ✅ |
| Citation cards (expand/collapse) | ✅ |
| Citation confidence score | ✅ |
| Strategy badge (graph/vector/hybrid) | ✅ |
| Copy message / citation to clipboard | ✅ |
| Animated splash screen | ✅ |
| Onboarding flow | ✅ |
| Floating glassmorphism nav bar | ✅ |
| Dark theme throughout | ✅ |
| Shimmer loading states | ✅ |
| Error banners with shake animation | ✅ |
| Logout with confirmation | ✅ |
