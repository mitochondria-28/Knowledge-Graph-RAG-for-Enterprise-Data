import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class StorageService {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const _tokenKey = 'jwt_token';
  static const _userKey  = 'user_json';

  static Future<void> saveToken(String token) =>
      _storage.write(key: _tokenKey, value: token);

  static Future<String?> getToken() => _storage.read(key: _tokenKey);

  static Future<void> deleteToken() => _storage.delete(key: _tokenKey);

  static Future<void> saveUser(String userJson) =>
      _storage.write(key: _userKey, value: userJson);

  static Future<String?> getUser() => _storage.read(key: _userKey);

  static Future<void> deleteUser() => _storage.delete(key: _userKey);

  static Future<void> clearAll() => _storage.deleteAll();
}
