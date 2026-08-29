class AppConfig {
  static const String baseUrl = 'https://enterprise-kg-rag.vercel.app';

  // Replace with your actual Google OAuth client ID (Android / iOS)
  static const String googleClientId =
      '906782144723-f8sjvua8d70q9di4h8nmqe6nshklvaa7.apps.googleusercontent.com';

  static const Duration connectTimeout = Duration(seconds: 30);
  static const Duration receiveTimeout = Duration(seconds: 60);

  static const int maxUploadBytes = 10 * 1024 * 1024; // 10 MB

  static const List<String> supportedExtensions = ['.pdf', '.md', '.txt'];

  static const List<String> docTypes = [
    'general',
    'company',
    'project',
    'technology',
    'people',
  ];
}
