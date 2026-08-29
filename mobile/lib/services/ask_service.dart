import '../models/ask_model.dart';
import 'api_client.dart';

class AskService {
  static Future<AskResponse> ask({
    required String question,
    int topK = 5,
  }) async {
    final resp = await ApiClient.instance.post('/ask', data: {
      'question': question,
      'top_k': topK,
    });
    return AskResponse.fromJson(resp.data as Map<String, dynamic>);
  }
}
