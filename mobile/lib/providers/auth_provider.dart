import 'package:flutter/material.dart';
import '../models/user_model.dart';
import '../services/auth_service.dart';

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthProvider extends ChangeNotifier {
  AuthStatus _status = AuthStatus.unknown;
  UserModel? _user;
  String? _error;

  AuthStatus get status => _status;
  UserModel? get user => _user;
  String? get error => _error;
  bool get isLoading => _status == AuthStatus.unknown;

  Future<void> restore() async {
    try {
      final user = await AuthService.restoreSession();
      if (user != null) {
        _user = user;
        _status = AuthStatus.authenticated;
      } else {
        _status = AuthStatus.unauthenticated;
      }
    } catch (_) {
      _status = AuthStatus.unauthenticated;
    }
    notifyListeners();
  }

  Future<bool> login(String email, String password) async {
    _error = null;
    try {
      final result = await AuthService.login(email: email, password: password);
      await AuthService.persist(result);
      _user = result.user;
      _status = AuthStatus.authenticated;
      notifyListeners();
      return true;
    } catch (e) {
      _error = _extractError(e);
      notifyListeners();
      return false;
    }
  }

  Future<bool> register(String email, String password, String name) async {
    _error = null;
    try {
      final result = await AuthService.register(email: email, password: password, name: name);
      await AuthService.persist(result);
      _user = result.user;
      _status = AuthStatus.authenticated;
      notifyListeners();
      return true;
    } catch (e) {
      _error = _extractError(e);
      notifyListeners();
      return false;
    }
  }

  Future<bool> loginWithGoogle(String idToken) async {
    _error = null;
    try {
      final result = await AuthService.loginWithGoogle(idToken);
      await AuthService.persist(result);
      _user = result.user;
      _status = AuthStatus.authenticated;
      notifyListeners();
      return true;
    } catch (e) {
      _error = _extractError(e);
      notifyListeners();
      return false;
    }
  }

  Future<void> logout() async {
    await AuthService.logout();
    _user = null;
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  String _extractError(dynamic e) {
    try {
      return e.response?.data['detail'] ?? e.toString();
    } catch (_) {
      return e.toString();
    }
  }
}
