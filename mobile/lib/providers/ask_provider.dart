import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import '../models/ask_model.dart';
import '../services/ask_service.dart';

class AskProvider extends ChangeNotifier {
  final List<ChatMessage> _messages = [];
  bool _isThinking = false;
  String? _error;

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  bool get isThinking => _isThinking;
  String? get error => _error;

  final _uuid = const Uuid();

  Future<void> ask(String question) async {
    if (question.trim().isEmpty) return;

    final userMsg = ChatMessage(
      id: _uuid.v4(),
      role: MessageRole.user,
      text: question.trim(),
    );
    _messages.add(userMsg);

    final thinkingMsg = ChatMessage(
      id: _uuid.v4(),
      role: MessageRole.assistant,
      text: '',
      isLoading: true,
    );
    _messages.add(thinkingMsg);

    _isThinking = true;
    _error = null;
    notifyListeners();

    try {
      final response = await AskService.ask(question: question.trim());
      _messages.remove(thinkingMsg);
      _messages.add(ChatMessage(
        id: _uuid.v4(),
        role: MessageRole.assistant,
        text: response.answer,
        response: response,
      ));
    } catch (e) {
      _messages.remove(thinkingMsg);
      _error = _msg(e);
      _messages.add(ChatMessage(
        id: _uuid.v4(),
        role: MessageRole.assistant,
        text: '⚠️ $_error',
      ));
    } finally {
      _isThinking = false;
      notifyListeners();
    }
  }

  void clear() {
    _messages.clear();
    _error = null;
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
