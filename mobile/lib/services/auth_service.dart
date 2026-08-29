import 'dart:convert';
import '../models/user_model.dart';
import 'api_client.dart';
import 'storage_service.dart';

class AuthResult {
  final String token;
  final UserModel user;
  const AuthResult({required this.token, required this.user});
}

class AuthService {
  static Future<AuthResult> register({
    required String email,
    required String password,
    required String name,
  }) async {
    final resp = await ApiClient.instance.post('/auth/register', data: {
      'email': email,
      'password': password,
      'name': name,
    });
    return _parseResult(resp.data);
  }

  static Future<AuthResult> login({
    required String email,
    required String password,
  }) async {
    final resp = await ApiClient.instance.post('/auth/login', data: {
      'email': email,
      'password': password,
    });
    return _parseResult(resp.data);
  }

  static Future<AuthResult> loginWithGoogle(String idToken) async {
    final resp = await ApiClient.instance.post('/auth/google', data: {
      'token': idToken,
    });
    return _parseResult(resp.data);
  }

  static Future<UserModel> getMe() async {
    final resp = await ApiClient.instance.get('/auth/me');
    return UserModel.fromJson(resp.data as Map<String, dynamic>);
  }

  static Future<void> persist(AuthResult result) async {
    await StorageService.saveToken(result.token);
    await StorageService.saveUser(jsonEncode(result.user.toJson()));
  }

  static Future<UserModel?> restoreSession() async {
    final userJson = await StorageService.getUser();
    final token    = await StorageService.getToken();
    if (userJson == null || token == null) return null;
    try {
      return UserModel.fromJson(jsonDecode(userJson) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  static Future<void> logout() => StorageService.clearAll();

  static AuthResult _parseResult(dynamic data) {
    final map = data as Map<String, dynamic>;
    return AuthResult(
      token: map['access_token'] as String,
      user: UserModel.fromJson(map['user'] as Map<String, dynamic>),
    );
  }
}
