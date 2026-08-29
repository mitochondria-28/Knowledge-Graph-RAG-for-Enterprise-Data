import 'package:dio/dio.dart';
import '../config/app_config.dart';
import 'storage_service.dart';

class ApiClient {
  static final Dio _dio = Dio(BaseOptions(
    baseUrl: AppConfig.baseUrl,
    connectTimeout: AppConfig.connectTimeout,
    receiveTimeout: AppConfig.receiveTimeout,
    headers: {'Content-Type': 'application/json'},
  ));

  static bool _interceptorAdded = false;

  static Dio get instance {
    if (!_interceptorAdded) {
      _dio.interceptors.add(InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await StorageService.getToken();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) {
          handler.next(error);
        },
      ));
      _interceptorAdded = true;
    }
    return _dio;
  }

  static String parseError(dynamic error) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map && data.containsKey('detail')) {
        return data['detail'].toString();
      }
      if (error.response?.statusCode == 401) return 'Session expired. Please log in again.';
      if (error.response?.statusCode == 400) return data?.toString() ?? 'Bad request';
      if (error.type == DioExceptionType.connectionTimeout ||
          error.type == DioExceptionType.receiveTimeout) {
        return 'Connection timed out. Check your network.';
      }
      if (error.type == DioExceptionType.connectionError) {
        return 'Could not reach the server. Check your internet connection.';
      }
    }
    return error.toString();
  }
}
