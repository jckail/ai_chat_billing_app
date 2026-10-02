import { chatSocketUrl, formatCurrency, messageId, tokenCount } from './endpoints';

test('chat transport follows configured HTTP or HTTPS backend origin', () => {
  expect(chatSocketUrl('http://localhost:8000/api', 1, 7)).toBe('ws://localhost:8000/ws/chat/1/7');
  expect(chatSocketUrl('https://backend.example/api/', 1, 7)).toBe('wss://backend.example/ws/chat/1/7');
  expect(() => chatSocketUrl('ftp://backend.example/api', 1, 7)).toThrow();
  expect(() => chatSocketUrl('https://user:pass@backend.example/api', 1, 7)).toThrow();
});

test('uses server IDs and reports missing costs without inventing prices', () => {
  expect(messageId({ message_id: 9 })).toBe(9);
  expect(messageId({ id: 8, message_id: 9 })).toBe(8);
  expect(formatCurrency(0.000013)).toBe('$0.000013');
  expect(formatCurrency(null)).toBe('Not available');
  expect(formatCurrency('invalid')).toBe('Not available');
});

test("REST token records and WebSocket counts render as numbers", () => {
  expect(tokenCount({ tokens: [{ token_type: "input", token_count: 4 }] })).toBe(4);
  expect(tokenCount({ token_count: 8 })).toBe(8);
  expect(tokenCount({})).toBeNull();
});
