import 'package:dio/dio.dart';
import '../models/document_model.dart';
import 'api_client.dart';

class DocumentService {
  static Future<List<DocumentModel>> listDocuments() async {
    final resp = await ApiClient.instance.get('/documents');
    final list = resp.data as List<dynamic>;
    return list
        .map((d) => DocumentModel.fromJson(d as Map<String, dynamic>))
        .toList();
  }

  static Future<Map<String, dynamic>> uploadDocument({
    required String filePath,
    required String fileName,
    required String docType,
    void Function(int, int)? onSendProgress,
  }) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(filePath, filename: fileName),
      'doc_type': docType,
    });

    final resp = await ApiClient.instance.post(
      '/documents/upload',
      data: formData,
      options: Options(contentType: 'multipart/form-data'),
      onSendProgress: onSendProgress,
    );
    return resp.data as Map<String, dynamic>;
  }
}
