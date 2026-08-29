class DocumentModel {
  final String filename;
  final String docType;
  final DateTime? uploadedAt;
  final int? sizeBytes;

  const DocumentModel({
    required this.filename,
    required this.docType,
    this.uploadedAt,
    this.sizeBytes,
  });

  factory DocumentModel.fromJson(Map<String, dynamic> json) => DocumentModel(
        filename: json['filename'] as String,
        docType: json['doc_type'] as String? ?? 'general',
        uploadedAt: json['uploaded_at'] != null
            ? DateTime.tryParse(json['uploaded_at'] as String)
            : null,
        sizeBytes: json['size_bytes'] as int?,
      );

  String get extension {
    final parts = filename.split('.');
    return parts.length > 1 ? '.${parts.last.toLowerCase()}' : '';
  }

  String get displaySize {
    if (sizeBytes == null) return '';
    final kb = sizeBytes! / 1024;
    if (kb < 1024) return '${kb.toStringAsFixed(1)} KB';
    return '${(kb / 1024).toStringAsFixed(1)} MB';
  }

  String get typeLabel {
    switch (docType) {
      case 'company':    return 'Company';
      case 'project':    return 'Project';
      case 'technology': return 'Technology';
      case 'people':     return 'People';
      default:           return 'General';
    }
  }
}
