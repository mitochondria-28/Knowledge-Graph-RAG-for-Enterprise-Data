import 'package:flutter/material.dart';
import '../models/document_model.dart';
import '../services/document_service.dart';

enum DocumentStatus { idle, loading, loaded, uploading, error }

class DocumentProvider extends ChangeNotifier {
  DocumentStatus _status = DocumentStatus.idle;
  List<DocumentModel> _documents = [];
  String? _error;
  double _uploadProgress = 0.0;
  String? _uploadResult;

  DocumentStatus get status => _status;
  List<DocumentModel> get documents => _documents;
  String? get error => _error;
  double get uploadProgress => _uploadProgress;
  String? get uploadResult => _uploadResult;
  bool get isLoading => _status == DocumentStatus.loading;
  bool get isUploading => _status == DocumentStatus.uploading;

  Future<void> fetchDocuments() async {
    _status = DocumentStatus.loading;
    _error = null;
    notifyListeners();
    try {
      _documents = await DocumentService.listDocuments();
      _status = DocumentStatus.loaded;
    } catch (e) {
      _error = _msg(e);
      _status = DocumentStatus.error;
    }
    notifyListeners();
  }

  Future<bool> uploadDocument({
    required String filePath,
    required String fileName,
    required String docType,
  }) async {
    _status = DocumentStatus.uploading;
    _uploadProgress = 0.0;
    _uploadResult = null;
    _error = null;
    notifyListeners();
    try {
      final result = await DocumentService.uploadDocument(
        filePath: filePath,
        fileName: fileName,
        docType: docType,
        onSendProgress: (sent, total) {
          _uploadProgress = total > 0 ? sent / total : 0;
          notifyListeners();
        },
      );
      final stats = result['stats'] as Map<String, dynamic>?;
      _uploadResult = stats != null
          ? 'Processed ${stats['chunks_created']} chunks from ${stats['documents_processed']} doc'
          : 'Upload successful';
      _status = DocumentStatus.loaded;
      await fetchDocuments();
      return true;
    } catch (e) {
      _error = _msg(e);
      _status = DocumentStatus.error;
      notifyListeners();
      return false;
    }
  }

  void clearUploadResult() {
    _uploadResult = null;
    notifyListeners();
  }

  String _msg(dynamic e) {
    try {
      return e.response?.data['detail'] ?? e.toString();
    } catch (_) {
      return e.toString();
    }
  }
}
